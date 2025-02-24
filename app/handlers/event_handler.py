import json
import time
import logging
import asyncio
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
        self.last_sent_length = 0  # Track the last sent content length
        self.loop = loop
        self.current_thread_id = None
        self.current_run_id = None
        self.is_complete = False
        self.has_started = False  # Track if we've started receiving content
        self.last_update_time = time.time()  # Track last content update
        self.last_ws_send_time = 0  # Track last WebSocket message send time
        self.ws_service = websocket_service
        self.openai_service = openai_service
        self.channel = channel
        if loop:
            self.ws_service.set_loop(loop)

    def on_event(self, event):
        """Handle different types of events from the assistant"""
        logger.debug(f"Received event: {event.event}")
        self.last_update_time = time.time()  # Update timestamp for any event

        if event.event == "thread.run.requires_action":
            self.current_thread_id = event.data.thread_id
            self.current_run_id = event.data.id
            self.has_started = True
            self.handle_tool_calls(event.data)

        elif event.event == "thread.message.delta":
            if hasattr(event.data.delta, "content") and event.data.delta.content:
                self.has_started = True
                content = event.data.delta.content[0].text.value
                self.message_content += content

                # Rate limit WebSocket messages to every 0.25 seconds
                current_time = time.time()
                if current_time - self.last_ws_send_time >= 0.25:
                    message_data = {
                        "message": self.message_content,
                        "timestamp": current_time,
                        "status": "in_progress",
                        "type": "response",
                    }

                    if self.loop:
                        try:
                            # Use run_until_complete to ensure ordered delivery
                            self.loop.run_until_complete(
                                self.ws_service.send_message(self.channel, message_data)
                            )
                            self.last_ws_send_time = current_time
                        except Exception as e:
                            logger.error(f"Error sending WebSocket message: {str(e)}")
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
                        "type": "response",
                    }
                    try:
                        # Use run_until_complete for final message too
                        self.loop.run_until_complete(
                            self.ws_service.send_message(self.channel, final_message)
                        )
                    except Exception as e:
                        logger.error(f"Error sending final WebSocket message: {str(e)}")
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

                # Create a future for the tool execution
                future = asyncio.run_coroutine_threadsafe(
                    registry.execute_function(tool.function.name, arguments), self.loop
                )

                try:
                    # Wait for the result with a timeout
                    result = future.result(timeout=60.0)  # 60 second timeout
                    logger.debug(f"Function result: {result}")

                    tool_outputs.append(
                        {
                            "tool_call_id": tool.id,
                            "output": (
                                json.dumps(result) if result is not None else "null"
                            ),
                        }
                    )
                except TimeoutError:
                    logger.error(f"Tool execution timed out for {tool.function.name}")
                    # Cancel the future if it timed out
                    future.cancel()
                    tool_outputs.append(
                        {
                            "tool_call_id": tool.id,
                            "output": "The operation took too long to complete. Please try again.",
                        }
                    )
            except Exception as e:
                logger.error(f"Error executing function: {str(e)}")
                user_friendly_message = (
                    "I had trouble retrieving the information you requested."
                )
                if "database" in str(e).lower():
                    user_friendly_message = "I'm having trouble accessing the database. Please try again in a moment."
                elif "not found" in str(e).lower():
                    user_friendly_message = "I couldn't find the information you requested. Please check your query and try again."
                elif "invalid" in str(e).lower():
                    user_friendly_message = "Some of the information provided was invalid. Please check and try again."

                tool_outputs.append(
                    {
                        "tool_call_id": tool.id,
                        "output": user_friendly_message,
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
            raise

    def on_error(self, error):
        """Handle errors during event processing"""
        logger.error(f"Error in event handler: {error}")
        if self.loop and self.ws_service:
            try:
                # Convert technical error to user-friendly message
                user_friendly_message = (
                    "I encountered an issue while processing your request."
                )

                if "rate limit" in str(error).lower():
                    user_friendly_message = "I'm receiving too many requests right now. Please try again in a moment."
                elif "timeout" in str(error).lower():
                    user_friendly_message = (
                        "The request took too long to process. Please try again."
                    )
                elif "connection" in str(error).lower():
                    user_friendly_message = "I'm having trouble connecting to my services. Please try again in a moment."
                elif "invalid" in str(error).lower():
                    user_friendly_message = (
                        "There was an issue with your request format. Please try again."
                    )
                elif "not found" in str(error).lower():
                    user_friendly_message = (
                        "The conversation thread was not found or may have expired."
                    )
                elif "processing" in str(error).lower():
                    user_friendly_message = (
                        "I had trouble processing your request. Please try again."
                    )
                elif "tool execution" in str(error).lower():
                    user_friendly_message = (
                        "I had trouble executing one of my tools. Please try again."
                    )

                error_message = {
                    "message": user_friendly_message,
                    "timestamp": time.time(),
                    "status": "error",
                    "type": "error",
                    "error_details": str(error),
                }

                # Use create_task instead of run_until_complete
                self.loop.create_task(
                    self.ws_service.send_message(self.channel, error_message)
                )
            except Exception as e:
                logger.error(f"Error sending error message: {str(e)}")
