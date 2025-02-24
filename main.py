# Standard library imports
import asyncio
import json
import logging
import signal
import threading
import time
import uuid
from contextlib import contextmanager

# Third-party imports
import pika

# Local imports
from app.core.config import settings
from app.services.openai_service import OpenAIService
from app.services.websocket_service import WebSocketService
from app.handlers.event_handler import CosmoEventHandler
from app.tools.registry import registry
from app.tools.weather import WeatherTool
from app.tools.kmc_active_clients import KMCActiveClientsTool
from app.tools.kmc_available_offices import KMCAvailableOfficesTool

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
        channel (str): The thread ID to use for the conversation
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

            # Create message with user's input using the channel as thread_id
            message = openai_service.create_message(channel, message)
            logger.info(f"Created message: {message.id}")

            # Start conversation stream
            logger.info("Starting conversation stream...")
            openai_service.stream_conversation(
                thread_id=channel,
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
    # Generate a unique consumer tag for this worker instance
    consumer_tag = f"cosmo_worker_{uuid.uuid4().hex[:8]}"

    while True:
        connection = None
        try:
            # Modified connection parameters optimized for multiple workers
            parameters = pika.URLParameters(RABBITMQ_URL)
            parameters.heartbeat = (
                15  # 15 second heartbeat - more responsive for multiple workers
            )
            parameters.blocked_connection_timeout = (
                10  # 10 second timeout for blocked connections
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            logger.info(f"[✓] Worker {consumer_tag} connected to RabbitMQ")
            logger.info(f"[✓] Queue Name: {QUEUE_NAME}")
            logger.info(f"[✓] Routing Key: {ROUTING_KEY}")

            # Declare main exchange first
            channel.exchange_declare(
                exchange=EXCHANGE_NAME, exchange_type="direct", durable=True
            )
            logger.info(f"[✓] Declared main exchange: {EXCHANGE_NAME}")

            # Declare dead letter exchange
            channel.exchange_declare(
                exchange=f"{EXCHANGE_NAME}_dlx", exchange_type="direct", durable=True
            )
            logger.info(f"[✓] Declared DLX exchange: {EXCHANGE_NAME}_dlx")

            # Now declare queue with settings optimized for multiple consumers
            queue = channel.queue_declare(
                queue=QUEUE_NAME,
                durable=True,  # Survive broker restarts
                arguments={
                    "x-max-priority": 10,  # Enable message priority
                    "x-message-ttl": 3600000,  # Messages expire after 1 hour
                    "x-dead-letter-exchange": f"{EXCHANGE_NAME}_dlx",  # Dead letter exchange for failed messages
                },
            )
            queue_name = queue.method.queue
            logger.info(f"[✓] Declared queue: {queue_name}")

            # Declare dead letter queue
            channel.queue_declare(queue=f"{QUEUE_NAME}_failed", durable=True)
            logger.info(f"[✓] Declared failed messages queue: {QUEUE_NAME}_failed")

            # Bind queues to exchanges
            channel.queue_bind(
                exchange=EXCHANGE_NAME, queue=queue_name, routing_key=ROUTING_KEY
            )
            channel.queue_bind(
                exchange=f"{EXCHANGE_NAME}_dlx",
                queue=f"{QUEUE_NAME}_failed",
                routing_key=ROUTING_KEY,
            )
            logger.info(f"[✓] Bound queues to exchanges")

            def callback(ch, method, properties, body):
                try:
                    # Process message with timeout
                    with timeout(10):  # 10 seconds timeout
                        try:
                            message_data = json.loads(body)
                        except json.JSONDecodeError as e:
                            error_msg = "The message format is invalid. Please check your request and try again."
                            logger.error(
                                f"Worker {consumer_tag} - JSON parse error: {str(e)}"
                            )

                            # Send error response if reply_to is provided
                            if properties.reply_to:
                                error_response = {"success": False, "error": error_msg}
                                ch.basic_publish(
                                    exchange="",
                                    routing_key=properties.reply_to,
                                    body=json.dumps(error_response),
                                )

                            # Reject without requeue
                            ch.basic_reject(
                                delivery_tag=method.delivery_tag, requeue=False
                            )
                            return

                        success, should_requeue, error_msg = process_message(
                            message_data, properties
                        )

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

                            # Convert technical error to user-friendly message
                            user_friendly_message = (
                                "I encountered an issue while processing your request."
                            )
                            if "missing" in error_msg.lower():
                                user_friendly_message = "Some required information is missing from your request. Please make sure to include all necessary details."
                            elif "invalid" in error_msg.lower():
                                user_friendly_message = "Some of the information provided was invalid. Please check and try again."
                            elif "timeout" in error_msg.lower():
                                user_friendly_message = "The request took too long to process. Please try again."
                            elif "connection" in error_msg.lower():
                                user_friendly_message = "I'm having trouble connecting to my services. Please try again in a moment."

                            # Send error via WebSocket
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
                                    "message": user_friendly_message,
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

                            ch.basic_reject(
                                delivery_tag=method.delivery_tag, requeue=False
                            )

                except TimeoutError:
                    error_msg = "Your request took too long to process. Please try again with a simpler query."
                    logger.warning(f"⌛ Timeout error")

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
                    error_msg = "An unexpected error occurred. Our team has been notified and is working on it."
                    logger.error(
                        f"Worker {consumer_tag} - Unexpected error in callback: {str(e)}"
                    )

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

            # Set up consumer with prefetch count of 1 to ensure fair dispatch across workers
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=queue_name,
                on_message_callback=callback,
                auto_ack=False,
                consumer_tag=consumer_tag,  # Add consumer tag for identification
            )

            logger.info(
                f"[*] Worker {consumer_tag} waiting for messages. To exit press CTRL+C"
            )
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError:
            logger.error(f"Worker {consumer_tag} - Connection lost, reconnecting...")
            time.sleep(5)  # Wait before reconnecting
        except KeyboardInterrupt:
            logger.info(f"Worker {consumer_tag} stopped by user")
            break
        except Exception as e:
            logger.error(f"Worker {consumer_tag} - Unexpected error: {str(e)}")
            time.sleep(5)  # Wait before retrying
        finally:
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception as e:
                    logger.error(
                        f"Worker {consumer_tag} - Error closing connection: {str(e)}"
                    )


if __name__ == "__main__":
    main()
