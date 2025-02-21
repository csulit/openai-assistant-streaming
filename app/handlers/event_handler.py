import json
import time
import logging
from typing import Dict, Any, Optional
from openai import AssistantEventHandler
from ..services.websocket_service import WebSocketService
from ..services.openai_service import OpenAIService
from ..tools.registry import registry

logger = logging.getLogger(__name__)


class CosmoEventHandler(AssistantEventHandler):
    """Event handler for Cosmo assistant"""

    def __init__(
        self,
        websocket_service: WebSocketService,
        openai_service: OpenAIService,
        channel: str,
        loop=None,
    ):
        super().__init__()
        self._stream = None
        self.message_content = ""
        self.loop = loop
        self.current_thread_id = None
        self.current_run_id = None
        self.is_complete = False
        self.ws_service = websocket_service
        self.openai_service = openai_service
        self.channel = channel
        if loop:
            self.ws_service.set_loop(loop)

    def on_event(self, event):
        """Handle different types of events from the assistant"""
        logger.debug(f"Received event: {event.event}")

        if event.event == "thread.run.requires_action":
            self.current_thread_id = event.data.thread_id
            self.current_run_id = event.data.id
            self.handle_tool_calls(event.data)

        elif event.event == "thread.message.delta":
            time.sleep(0.05)  # Small delay to allow message processing
            if hasattr(event.data.delta, "content") and event.data.delta.content:
                content = event.data.delta.content[0].text.value
                self.message_content += content

                message_data = {
                    "message": self.message_content,
                    "timestamp": time.time(),
                    "status": "in_progress",
                }

                if self.loop:
                    logger.debug(
                        f"Sending message via WebSocket: {json.dumps(message_data)}"
                    )
                    self.loop.run_until_complete(
                        self.ws_service.send_message(self.channel, message_data)
                    )
                else:
                    logger.warning("No event loop available for WebSocket message")

        elif event.event == "thread.message.completed":
            if hasattr(event.data, "content") and event.data.content:
                logger.info("Message completed, sending final message")
                if self.loop:
                    final_message = {
                        "message": self.message_content,
                        "timestamp": time.time(),
                        "status": "completed",
                    }
                    self.loop.run_until_complete(
                        self.ws_service.send_message(self.channel, final_message)
                    )
                else:
                    logger.warning("No event loop available for final message")

        elif event.event == "thread.run.completed":
            logger.info("Run completed")
            self.is_complete = True

    def handle_tool_calls(self, data):
        """Handle tool calls from the assistant"""
        tool_outputs = []
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            try:
                arguments = json.loads(tool.function.arguments)
                logger.info(
                    f"Executing function: {tool.function.name} with arguments: {arguments}"
                )

                result = self.loop.run_until_complete(
                    registry.execute_function(tool.function.name, arguments)
                )
                logger.debug(f"Function result: {result}")

                tool_outputs.append(
                    {
                        "tool_call_id": tool.id,
                        "output": json.dumps(result) if result is not None else "null",
                    }
                )
            except Exception as e:
                logger.error(f"Error executing function: {str(e)}")
                tool_outputs.append(
                    {
                        "tool_call_id": tool.id,
                        "output": f"Error executing function: {str(e)}",
                    }
                )

        logger.debug("Submitting tool outputs:", tool_outputs)
        self.submit_tool_outputs(tool_outputs)

    def submit_tool_outputs(self, tool_outputs):
        """Submit tool outputs back to the assistant"""
        try:
            if self.current_thread_id and self.current_run_id:
                # Create new event handler with the same loop
                new_handler = CosmoEventHandler(
                    self.ws_service, self.openai_service, self.channel, self.loop
                )

                self.openai_service.submit_tool_outputs(
                    thread_id=self.current_thread_id,
                    run_id=self.current_run_id,
                    tool_outputs=tool_outputs,
                    event_handler=new_handler,
                )
                logger.info("Tool outputs submitted successfully")
            else:
                logger.error("Missing thread_id or run_id")
        except Exception as e:
            logger.error(f"Error submitting tool outputs: {str(e)}")

    def on_error(self, error):
        """Handle errors during event processing"""
        logger.error(f"Error in event handler: {error}")
        if self.loop and self.ws_service:
            try:
                error_message = {
                    "message": "I encountered an issue while processing your request. Please try again.",
                    "error": str(error),
                    "timestamp": time.time(),
                    "status": "error",
                    "type": "error",
                }
                logger.debug(
                    f"Sending error message to WebSocket: {json.dumps(error_message)}"
                )
                self.loop.run_until_complete(
                    self.ws_service.send_message(self.channel, error_message)
                )
            except Exception as e:
                logger.error(f"Error sending error message: {str(e)}")
