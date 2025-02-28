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
        message_id=None,
        thread_id=None,
    ):
        super().__init__()
        self._stream = None
        self.message_content = ""
        self.last_sent_length = 0  # Track the last sent content length
        self.loop = loop
        self.current_thread_id = thread_id  # Initialize with provided thread_id
        self.current_run_id = None
        self.is_complete = False
        self.has_started = False  # Track if we've started receiving content
        self.last_update_time = time.time()  # Track last content update
        self.last_ws_send_time = 0  # Track last WebSocket message send time
        self.ws_service = websocket_service
        self.openai_service = openai_service
        self.channel = channel
        self.message_id = message_id  # Store the message_id
        self.accumulated_content = ""  # Buffer for accumulating content
        self.min_chunk_size = 10  # Minimum characters before sending
        if loop:
            self.ws_service.set_loop(loop)
        # Send initial status message
        if loop and websocket_service:
            try:
                initial_message = {
                    "message": "Assistant is processing your request...",
                    "timestamp": time.time(),
                    "status": "started",
                    "type": "status",
                    "final_message": False,
                    "message_id": self.message_id,
                    "thread_id": self.current_thread_id,
                }
                loop.run_until_complete(
                    websocket_service.send_message(channel, initial_message)
                )
            except Exception as e:
                logger.error(f"Failed to send initial status message: {str(e)}")

    def on_event(self, event):
        """Handle different types of events from the assistant"""
        logger.debug(f"Received event: {event.event}")
        self.last_update_time = time.time()

        # Send initial status if this is the first event
        if not self.has_started:
            self.has_started = True
            if self.loop and self.ws_service:
                try:
                    status_message = {
                        "message": "Assistant is processing your request...",
                        "timestamp": time.time(),
                        "status": "started",
                        "type": "status",
                        "final_message": False,
                        "message_id": self.message_id,
                        "thread_id": self.current_thread_id,
                    }
                    self.loop.run_until_complete(
                        self.ws_service.send_message(self.channel, status_message)
                    )
                except Exception as e:
                    logger.error(f"Failed to send initial status: {str(e)}")

        if event.event == "thread.run.requires_action":
            # Update thread_id if available in the event
            if hasattr(event.data, "thread_id") and event.data.thread_id:
                self.current_thread_id = event.data.thread_id

            # Send tool execution status
            if self.loop and self.ws_service:
                try:
                    status_message = {
                        "message": "Assistant is gathering information...",
                        "timestamp": time.time(),
                        "status": "processing",
                        "type": "status",
                        "final_message": False,
                        "message_id": self.message_id,
                        "thread_id": self.current_thread_id,
                    }
                    self.loop.run_until_complete(
                        self.ws_service.send_message(self.channel, status_message)
                    )
                except Exception as e:
                    logger.error(f"Failed to send tool execution status: {str(e)}")

            self.current_run_id = event.data.id
            self.handle_tool_calls(event.data)

        elif event.event == "thread.message.delta":
            # Send responding status on first delta
            if not hasattr(self, "_sent_responding_status"):
                self._sent_responding_status = True
                if self.loop and self.ws_service:
                    try:
                        status_message = {
                            "message": "Assistant is responding...",
                            "timestamp": time.time(),
                            "status": "responding",
                            "type": "status",
                            "final_message": False,
                            "message_id": self.message_id,
                            "thread_id": self.current_thread_id,
                        }
                        self.loop.run_until_complete(
                            self.ws_service.send_message(self.channel, status_message)
                        )
                    except Exception as e:
                        logger.error(f"Failed to send response status: {str(e)}")

            if hasattr(event.data.delta, "content") and event.data.delta.content:
                content = event.data.delta.content[0].text.value
                self.message_content += content
                print(content, end="", flush=True)

                self.accumulated_content += content
                current_time = time.time()
                should_send = (
                    len(self.accumulated_content) >= self.min_chunk_size
                    or (current_time - self.last_ws_send_time) >= 1.0
                )

                if should_send and self.accumulated_content:
                    message_data = {
                        "message": self.message_content,
                        "timestamp": current_time,
                        "status": "in_progress",
                        "type": "response",
                        "final_message": False,
                        "message_id": self.message_id,
                        "thread_id": self.current_thread_id,
                    }

                    if self.loop:
                        try:
                            self.loop.run_until_complete(
                                self.ws_service.send_message(self.channel, message_data)
                            )
                            self.last_ws_send_time = current_time
                            self.accumulated_content = ""  # Clear accumulated content
                        except Exception as e:
                            logger.error(f"Failed to send WebSocket message: {str(e)}")
                    else:
                        logger.warning("No event loop available for WebSocket message")

        elif event.event == "thread.message.completed":
            logger.info("Message completed")
            print()  # New line after content
            if self.loop:
                final_message = {
                    "message": self.message_content,
                    "timestamp": time.time(),
                    "status": "completed",
                    "type": "response",
                    "final_message": True,
                    "message_id": self.message_id,
                    "thread_id": self.current_thread_id,
                }
                try:
                    self.loop.run_until_complete(
                        self.ws_service.send_message(self.channel, final_message)
                    )
                except Exception as e:
                    logger.error(f"Failed to send final message: {str(e)}")
            self.is_complete = True
            # Force cleanup
            if self.loop and self.ws_service:
                try:
                    self.loop.run_until_complete(self.ws_service.disconnect())
                except Exception as e:
                    logger.error(f"Failed to disconnect WebSocket: {str(e)}")

        elif event.event == "thread.run.completed":
            logger.info("Run completed")
            self.is_complete = True
            # Force cleanup here as well
            if self.loop and self.ws_service:
                try:
                    self.loop.run_until_complete(self.ws_service.disconnect())
                except Exception as e:
                    logger.error(f"Failed to disconnect WebSocket: {str(e)}")

    def handle_tool_calls(self, data):
        """Handle tool calls from the assistant"""
        tool_outputs = []
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            try:
                arguments = json.loads(tool.function.arguments)
                logger.info(
                    f"Executing function: {tool.function.name} with arguments: {arguments}"
                )

                # Execute the function
                result = None
                try:
                    result = self.loop.run_until_complete(
                        registry.execute_function(tool.function.name, arguments)
                    )
                    logger.debug(f"Function result: {result}")
                except TimeoutError:
                    logger.error(f"Tool execution timed out for {tool.function.name}")
                    result = (
                        "The operation took too long to complete. Please try again."
                    )
                except Exception as e:
                    logger.error(f"Error executing function: {str(e)}")
                    result = str(e)

                tool_outputs.append(
                    {
                        "tool_call_id": tool.id,
                        "output": json.dumps(result) if result is not None else "null",
                    }
                )

            except Exception as e:
                logger.error(f"Error in tool execution: {str(e)}")
                tool_outputs.append(
                    {
                        "tool_call_id": tool.id,
                        "output": str(e),
                    }
                )

        # Submit tool outputs with a new handler instance
        if self.current_thread_id and self.current_run_id:
            try:
                # Create a new handler for tool output submission
                new_handler = CosmoEventHandler(
                    self.ws_service,
                    self.openai_service,
                    self.channel,
                    self.loop,
                    self.message_id,  # Pass the message_id to the new handler
                    self.current_thread_id,  # Pass the current_thread_id to the new handler
                )
                # Copy over the necessary state
                new_handler.message_content = self.message_content
                new_handler.current_thread_id = self.current_thread_id
                new_handler.current_run_id = self.current_run_id

                self.openai_service.submit_tool_outputs(
                    thread_id=self.current_thread_id,
                    run_id=self.current_run_id,
                    tool_outputs=tool_outputs,
                    event_handler=new_handler,  # Use the new handler instance
                )
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
                    "message_id": self.message_id,
                    "thread_id": self.current_thread_id,
                }

                try:
                    self.loop.run_until_complete(
                        self.ws_service.send_message(self.channel, error_message)
                    )
                except Exception as e:
                    logger.error(f"Error sending error message: {str(e)}")
            except Exception as e:
                logger.error(f"Error preparing error message: {str(e)}")
