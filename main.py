import pika
import json
import time
import asyncio
import logging
import signal
from contextlib import contextmanager
from typing import Optional
from app.core.config import settings
from app.services.openai_service import OpenAIService
from app.services.websocket_service import WebSocketService
from app.handlers.event_handler import CosmoEventHandler
from app.tools.registry import registry
from app.tools.weather import WeatherTool
from app.tools.kmc_active_clients import KMCActiveClientsTool
from app.tools.kmc_available_offices import KMCAvailableOfficesTool
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RabbitMQ Configuration
RABBITMQ_URL = settings.RABBITMQ_URL
QUEUE_NAME = settings.QUEUE_NAME
ROUTING_KEY = settings.ROUTING_KEY
EXCHANGE_NAME = settings.EXCHANGE_NAME

# Add this at the top level with other globals
conversation_lock = threading.Lock()


def initialize_tools():
    """Initialize and register all tools"""
    weather_tool = WeatherTool(settings.OPENWEATHER_API_KEY)
    active_clients_tool = KMCActiveClientsTool()
    available_offices_tool = KMCAvailableOfficesTool()

    registry.register(weather_tool)
    registry.register(active_clients_tool)
    registry.register(available_offices_tool)

    return registry.get_function_definitions()


@contextmanager
def timeout(seconds: int):
    """Context manager for timeout"""

    def signal_handler(signum, frame):
        raise TimeoutError("Processing timed out")

    # Set the signal handler and a timeout
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)

    try:
        yield
    finally:
        # Disable the alarm
        signal.alarm(0)


def run_conversation(
    message: str,
    channel: str,
    properties=None,
) -> tuple[bool, str]:
    """Run the main conversation loop

    Args:
        message (str): The user's message to start the conversation
        channel (str): The WebSocket channel to use for communication
        properties: RabbitMQ message properties for potential reply handling

    Returns:
        tuple[bool, str]: (success, error_message)
        - success: True if conversation completed successfully
        - error_message: Description of error if any, empty string if successful
    """
    # Try to acquire the lock, return if already running
    if not conversation_lock.acquire(blocking=False):
        error_msg = "Another conversation is already in progress"
        logger.warning(error_msg)
        return False, error_msg

    try:
        # Create and initialize event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Initialize services
            openai_service = OpenAIService()
            websocket_service = WebSocketService()

            # Initialize tools
            function_definitions = initialize_tools()

            # Initialize WebSocket connection and subscribe to channel
            try:
                loop.run_until_complete(websocket_service.connect())
            except Exception as e:
                error_msg = f"Failed to connect to WebSocket server: {str(e)}"
                logger.error(error_msg)
                return False, error_msg

            try:
                loop.run_until_complete(websocket_service.subscribe(channel))
            except Exception as e:
                error_msg = (
                    f"Failed to subscribe to WebSocket channel {channel}: {str(e)}"
                )
                logger.error(error_msg)
                return False, error_msg

            # Initialize event handler with both services and channel
            event_handler = CosmoEventHandler(
                websocket_service, openai_service, channel, loop
            )

            # Create assistant
            assistant = openai_service.create_assistant(function_definitions)

            # Create conversation thread
            thread = openai_service.create_thread()
            logger.info(f"Created thread: {thread.id}")

            # Create message with user's input
            message = openai_service.create_message(thread.id, message)
            logger.info(f"Created message: {message.id}")

            # Start conversation stream
            logger.info("Starting conversation stream...")
            openai_service.stream_conversation(
                thread_id=thread.id,
                assistant_id=assistant.id,
                event_handler=event_handler,
            )

            # Wait for completion or timeout
            start_time = time.time()
            while not event_handler.is_complete:
                if (
                    time.time() - start_time > 25
                ):  # 25 second timeout (less than the 30s global timeout)
                    raise TimeoutError("Conversation timed out waiting for completion")
                time.sleep(0.1)  # Small sleep to prevent CPU spinning

            logger.info("Conversation completed successfully")
            return True, ""

        except TimeoutError as e:
            error_msg = str(e)
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error in conversation: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
        finally:
            # Cleanup
            if "assistant" in locals():
                openai_service.delete_assistant(assistant.id)
            if loop:
                loop.run_until_complete(websocket_service.disconnect())
                loop.close()

    finally:
        # Always release the lock
        conversation_lock.release()


def process_message(message_data: dict, properties=None) -> tuple[bool, bool, str]:
    """Process a message from RabbitMQ

    Args:
        message_data (dict): The message data from RabbitMQ
        properties: RabbitMQ message properties

    Returns:
        tuple[bool, bool, str]: (success, should_requeue, error_message)
        - success: True if processed successfully
        - should_requeue: True if message should be requeued on failure
        - error_message: Description of error if any, empty string if successful
    """
    try:
        # Extract required fields from message_data
        user_message = message_data.get("message")
        if not isinstance(user_message, str):
            error_msg = "Invalid or missing 'message' field"
            logger.error(error_msg)
            return False, False, error_msg

        # Validate channel (now required)
        channel = message_data.get("channel")
        if not channel:
            error_msg = "Missing required 'channel' field"
            logger.error(error_msg)
            return False, False, error_msg

        if not isinstance(channel, str):
            error_msg = "Invalid 'channel' field"
            logger.error(error_msg)
            return False, False, error_msg

        # Validate channel values
        valid_channels = {"weather-update", "business-update", "sales-update"}
        if channel not in valid_channels:
            error_msg = (
                f"Invalid channel value: {channel}. Must be one of {valid_channels}"
            )
            logger.error(error_msg)
            return False, False, error_msg

        # Run the conversation
        conversation_success, error_msg = run_conversation(
            message=user_message, channel=channel, properties=properties
        )
        return (
            conversation_success,
            True,
            error_msg,
        )  # Only requeue if it's a processing error

    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {str(e)}"
        logger.error(error_msg)
        return False, False, error_msg
    except Exception as e:
        error_msg = f"Error processing message: {str(e)}"
        logger.error(error_msg)
        return False, True, error_msg  # Requeue on unexpected errors


def main():
    """Main RabbitMQ consumer loop"""
    while True:
        connection = None
        try:
            # Modified connection parameters with heartbeat
            parameters = pika.URLParameters(RABBITMQ_URL)
            parameters.heartbeat = 60  # 60 second heartbeat
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            logger.info(f"[✓] Connected to RabbitMQ")
            logger.info(f"[✓] Queue Name: {QUEUE_NAME}")
            logger.info(f"[✓] Routing Key: {ROUTING_KEY}")

            # Declare queue and bind to exchange
            queue = channel.queue_declare(queue=QUEUE_NAME)
            queue_name = queue.method.queue

            channel.queue_bind(
                exchange=EXCHANGE_NAME, queue=queue_name, routing_key=ROUTING_KEY
            )

            def callback(ch, method, properties, body):
                try:
                    # Process message with timeout
                    with timeout(30):  # 30 seconds timeout
                        try:
                            message_data = json.loads(body)
                        except json.JSONDecodeError as e:
                            error_msg = f"Failed to parse message JSON: {str(e)}"
                            logger.error(error_msg)

                            # Send error response if reply_to is provided
                            if properties.reply_to:
                                error_response = {"success": False, "error": error_msg}
                                ch.basic_publish(
                                    exchange="",
                                    routing_key=properties.reply_to,
                                    body=json.dumps(error_response),
                                )

                            # Reject without requeue and send error via WebSocket
                            ch.basic_reject(
                                delivery_tag=method.delivery_tag, requeue=False
                            )
                            return

                        success, should_requeue, error_msg = process_message(
                            message_data, properties
                        )

                        # Create and initialize event loop for WebSocket error messages
                        error_loop = None
                        if not success:
                            try:
                                error_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(error_loop)
                                websocket_service = WebSocketService()
                                error_loop.run_until_complete(
                                    websocket_service.connect()
                                )
                                error_loop.run_until_complete(
                                    websocket_service.subscribe(message_data["channel"])
                                )

                                error_message = {
                                    "message": error_msg,
                                    "timestamp": time.time(),
                                    "status": "error",
                                    "type": "error",
                                }
                                error_loop.run_until_complete(
                                    websocket_service.send_message(
                                        message_data["channel"], error_message
                                    )
                                )
                            except Exception as ws_error:
                                logger.error(
                                    f"Failed to send error via WebSocket: {ws_error}"
                                )
                            finally:
                                if error_loop:
                                    error_loop.run_until_complete(
                                        websocket_service.disconnect()
                                    )
                                    error_loop.close()

                        # Send response if reply_to is provided
                        if properties.reply_to:
                            response = {
                                "success": success,
                                "error": error_msg if not success else "",
                            }
                            ch.basic_publish(
                                exchange="",
                                routing_key=properties.reply_to,
                                body=json.dumps(response),
                            )

                        if success:
                            # Message processed successfully
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            logger.info(
                                "✓ Message processed successfully and acknowledged"
                            )
                        else:
                            # Message processing failed - reject without requeue
                            logger.error(f"Processing failed: {error_msg}")
                            ch.basic_reject(
                                delivery_tag=method.delivery_tag, requeue=False
                            )

                except TimeoutError:
                    error_msg = "Processing timed out"
                    logger.warning(f"⌛ {error_msg}")

                    try:
                        # Send timeout error via WebSocket
                        error_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(error_loop)
                        websocket_service = WebSocketService()
                        error_loop.run_until_complete(websocket_service.connect())
                        error_loop.run_until_complete(
                            websocket_service.subscribe(message_data["channel"])
                        )

                        error_message = {
                            "message": error_msg,
                            "timestamp": time.time(),
                            "status": "error",
                            "type": "error",
                        }
                        error_loop.run_until_complete(
                            websocket_service.send_message(
                                message_data["channel"], error_message
                            )
                        )
                    except Exception as ws_error:
                        logger.error(
                            f"Failed to send timeout error via WebSocket: {ws_error}"
                        )
                    finally:
                        if error_loop:
                            error_loop.run_until_complete(
                                websocket_service.disconnect()
                            )
                            error_loop.close()

                    # Send timeout error response if reply_to is provided
                    if properties.reply_to:
                        error_response = {"success": False, "error": error_msg}
                        ch.basic_publish(
                            exchange="",
                            routing_key=properties.reply_to,
                            body=json.dumps(error_response),
                        )

                    # Reject without requeue
                    ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)

                except Exception as e:
                    error_msg = f"Unexpected error in callback: {e}"
                    logger.error(error_msg)

                    try:
                        # Send unexpected error via WebSocket
                        error_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(error_loop)
                        websocket_service = WebSocketService()
                        error_loop.run_until_complete(websocket_service.connect())
                        error_loop.run_until_complete(
                            websocket_service.subscribe(message_data["channel"])
                        )

                        error_message = {
                            "message": error_msg,
                            "timestamp": time.time(),
                            "status": "error",
                            "type": "error",
                        }
                        error_loop.run_until_complete(
                            websocket_service.send_message(
                                message_data["channel"], error_message
                            )
                        )
                    except Exception as ws_error:
                        logger.error(f"Failed to send error via WebSocket: {ws_error}")
                    finally:
                        if error_loop:
                            error_loop.run_until_complete(
                                websocket_service.disconnect()
                            )
                            error_loop.close()

                    # Send error response if reply_to is provided
                    if properties.reply_to:
                        error_response = {"success": False, "error": error_msg}
                        ch.basic_publish(
                            exchange="",
                            routing_key=properties.reply_to,
                            body=json.dumps(error_response),
                        )

                    # Reject without requeue
                    ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)

            # Set up consumer with prefetch count of 1 to ensure one message at a time
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=queue_name, on_message_callback=callback, auto_ack=False
            )

            logger.info("[*] Waiting for messages. To exit press CTRL+C")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError:
            logger.error("Connection lost, reconnecting...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
            break
        finally:
            if connection and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
