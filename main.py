# Standard library imports
import asyncio
import json
import logging
import signal
import threading
import time
import uuid
from contextlib import contextmanager
import sys
import os

# Third-party imports
import pika
from openai import NotFoundError

# Local imports
from app.core.config import settings
from app.services.openai_service import OpenAIService
from app.services.websocket_service import WebSocketService
from app.handlers.event_handler import CosmoEventHandler
from app.tools.registry import registry
from app.tools.weather import WeatherTool
from app.tools.kmc_active_clients import KMCActiveClientsTool
from app.tools.kmc_available_offices import KMCAvailableOfficesTool
from app.tools.user_audit_tool import UserAuditTool
from app.tools.user_role_tool import UserRoleTool

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

# Initialize tools at startup
weather_tool = WeatherTool(settings.OPENWEATHER_API_KEY)
active_clients_tool = KMCActiveClientsTool()
available_offices_tool = KMCAvailableOfficesTool()
user_audit_tool = UserAuditTool()
user_role_tool = UserRoleTool()

tools = [
    weather_tool,
    active_clients_tool,
    available_offices_tool,
    user_audit_tool,
    user_role_tool
]

registry.register(weather_tool)
registry.register(active_clients_tool)
registry.register(available_offices_tool)
registry.register(user_audit_tool)
registry.register(user_role_tool)

function_definitions = registry.get_function_definitions()


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
    if not settings.OPENAI_ASSISTANT_ID:
        error_msg = "OPENAI_ASSISTANT_ID not configured. Please create an assistant first using --create-assistant"
        logger.error(error_msg)
        return False, error_msg

    # Try to acquire the lock, return if already running
    if not conversation_lock.acquire(blocking=False):
        error_msg = "Another conversation is already in progress"
        logger.warning(error_msg)
        return False, error_msg

    websocket_service = None
    loop = None
    try:
        # Create and initialize event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Initialize services
            openai_service = OpenAIService()
            websocket_service = WebSocketService()

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

            try:
                # Create message with user's input using the channel as thread_id
                message = openai_service.create_message(
                    channel, message, event_handler=event_handler
                )
                logger.info(f"Created message: {message.id}")

                # Start conversation stream
                logger.info("Starting conversation stream...")
                openai_service.stream_conversation(
                    thread_id=channel,
                    assistant_id=settings.OPENAI_ASSISTANT_ID,
                    event_handler=event_handler,
                )

                # Wait for completion or timeout
                start_time = time.time()
                last_update_time = start_time
                while not event_handler.is_complete:
                    current_time = time.time()

                    # Check if we've received any message content
                    if event_handler.last_update_time > last_update_time:
                        # Reset timeout if we're actively receiving content
                        last_update_time = event_handler.last_update_time
                    elif (
                        current_time - start_time > 45 and not event_handler.has_started
                    ):  # Increased from 25 to 45 seconds
                        # If we haven't received any response in 45 seconds
                        error_msg = "No response received from assistant"
                        logger.error(error_msg)
                        error_message = {
                            "message": "The assistant is taking too long to respond. Please try again.",
                            "timestamp": time.time(),
                            "status": "error",
                            "type": "timeout",
                            "error_details": error_msg,
                        }
                        loop.run_until_complete(
                            websocket_service.send_message(channel, error_message)
                        )
                        raise TimeoutError(error_msg)
                    elif (
                        current_time - last_update_time > 60
                    ):  # Increased from 30 to 60 seconds
                        # If we haven't received any updates in 60 seconds after starting
                        error_msg = "Response stream interrupted"
                        logger.error(error_msg)
                        error_message = {
                            "message": "The response was interrupted. Please try again.",
                            "timestamp": time.time(),
                            "status": "error",
                            "type": "timeout",
                            "error_details": error_msg,
                        }
                        loop.run_until_complete(
                            websocket_service.send_message(channel, error_message)
                        )
                        raise TimeoutError(error_msg)

                    time.sleep(0.1)  # Small sleep to prevent CPU spinning

                logger.info("Conversation completed successfully")
                return True, ""

            except NotFoundError as e:
                error_msg = "Thread not found or was deleted during conversation."
                logger.error(error_msg)
                error_message = {
                    "message": error_msg,
                    "timestamp": time.time(),
                    "status": "error",
                    "type": "error",
                    "error_details": str(e),
                }
                loop.run_until_complete(
                    websocket_service.send_message(channel, error_message)
                )
                return False, error_msg

        except TimeoutError as e:
            error_msg = str(e)
            logger.error(error_msg)
            if websocket_service:
                error_message = {
                    "message": "The request took too long to process. Please try again.",
                    "timestamp": time.time(),
                    "status": "error",
                    "type": "error",
                    "error_details": error_msg,
                }
                loop.run_until_complete(
                    websocket_service.send_message(channel, error_message)
                )
            return False, error_msg
        except Exception as e:
            error_msg = f"Error in conversation: {str(e)}"
            logger.error(error_msg)
            if websocket_service:
                error_message = {
                    "message": "An unexpected error occurred. Please try again.",
                    "timestamp": time.time(),
                    "status": "error",
                    "type": "error",
                    "error_details": error_msg,
                }
                loop.run_until_complete(
                    websocket_service.send_message(channel, error_message)
                )
            return False, error_msg
        finally:
            # Cleanup
            if websocket_service and loop:
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


def generate_test_thread():
    """Generate a test thread ID"""
    openai_service = OpenAIService()
    openai_service.create_thread()


def create_assistant():
    """Create a new assistant and get its ID"""
    openai_service = OpenAIService()
    openai_service.create_assistant_id(registry.get_function_definitions())


def delete_assistant(assistant_id: str):
    """Delete an assistant by ID"""
    openai_service = OpenAIService()
    openai_service.delete_assistant(assistant_id)


def test_message(thread_id: str, message: str):
    """Test sending a message directly to a thread

    Args:
        thread_id (str): The thread ID to send the message to
        message (str): The message to send
    """
    try:
        # Create event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Initialize services
        openai_service = OpenAIService()
        websocket_service = WebSocketService()

        # Connect to WebSocket
        loop.run_until_complete(websocket_service.connect())
        loop.run_until_complete(websocket_service.subscribe(thread_id))

        # Initialize event handler
        event_handler = CosmoEventHandler(
            websocket_service, openai_service, thread_id, loop
        )

        # Create and process message
        openai_service.create_message(thread_id, message, event_handler=event_handler)
        openai_service.stream_conversation(
            thread_id=thread_id,
            assistant_id=settings.OPENAI_ASSISTANT_ID,
            event_handler=event_handler,
        )

        # Wait for completion or timeout
        start_time = time.time()
        last_update_time = start_time

        while True:
            current_time = time.time()

            # Update last activity time if we're receiving content
            if event_handler.last_update_time > last_update_time:
                last_update_time = event_handler.last_update_time

            # Check for timeouts
            if current_time - start_time > 45 and not event_handler.has_started:
                print("\nTimeout: No response received from assistant")
                break
            elif current_time - last_update_time > 60:
                print("\nTimeout: Response stream interrupted")
                break

            # Check for completion
            if event_handler.is_complete:
                print("\nRun completed")
                break

            time.sleep(0.1)

    except Exception as e:
        print(f"\n=== ERROR ===\n{str(e)}\n============")


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
                success = False  # Track if processing was successful
                try:
                    # Process message with timeout
                    with timeout(90):  # Increased from 30 to 90 seconds timeout
                        try:
                            message_data = json.loads(body)
                        except json.JSONDecodeError as e:
                            error_msg = "The message format is invalid. Please check your request and try again."
                            logger.error(
                                f"Worker {consumer_tag} - JSON parse error: {str(e)}"
                            )
                            if properties.reply_to:
                                error_response = {"success": False, "error": error_msg}
                                ch.basic_publish(
                                    exchange="",
                                    routing_key=properties.reply_to,
                                    body=json.dumps(error_response),
                                )
                            ch.basic_reject(
                                delivery_tag=method.delivery_tag, requeue=False
                            )
                            return

                        success, should_requeue, error_msg = process_message(
                            message_data, properties
                        )

                        if success:
                            # Message processed successfully
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            logger.info(
                                "✓ Message processed successfully and acknowledged"
                            )
                            return  # Exit early on success

                        # Handle error cases
                        logger.error(f"Processing failed: {error_msg}")

                        # Send error via WebSocket
                        try:
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
                                "error_details": error_msg,
                            }
                            error_loop.run_until_complete(
                                websocket_service.send_message(
                                    message_data["channel"], error_message
                                )
                            )
                            error_loop.close()
                        except Exception as ws_error:
                            logger.error(
                                f"Failed to send error via WebSocket: {ws_error}"
                            )

                        # Reject without requeue
                        ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)

                except TimeoutError:
                    if not success:  # Only handle timeout if not already successful
                        error_msg = "The request is taking longer than expected to process. Please try again."
                        logger.warning(
                            f"⌛ Timeout error: Request processing exceeded 90 seconds"
                        )
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
                                "type": "timeout",
                                "error_details": "Processing exceeded 90 second timeout limit",
                            }
                            error_loop.run_until_complete(
                                websocket_service.send_message(
                                    message_data["channel"], error_message
                                )
                            )
                            error_loop.close()

                            # Reject without requeue
                            ch.basic_reject(
                                delivery_tag=method.delivery_tag, requeue=False
                            )
                        except Exception as ws_error:
                            logger.error(
                                f"Failed to send timeout error via WebSocket: {ws_error}"
                            )

                except Exception as e:
                    if not success:
                        error_msg = "An unexpected error occurred. Our team has been notified and is working on it."
                        logger.error(
                            f"Worker {consumer_tag} - Unexpected error in callback: {str(e)}"
                        )
                        try:
                            # Send error via WebSocket
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
                                "error_details": str(e),
                            }
                            error_loop.run_until_complete(
                                websocket_service.send_message(
                                    message_data["channel"], error_message
                                )
                            )
                            error_loop.close()

                            # Reject without requeue
                            ch.basic_reject(
                                delivery_tag=method.delivery_tag, requeue=False
                            )
                        except Exception as ws_error:
                            logger.error(
                                f"Failed to send error via WebSocket: {ws_error}"
                            )

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
    if len(sys.argv) > 1:
        if sys.argv[1] == "--generate-thread":
            generate_test_thread()
        elif sys.argv[1] == "--create-assistant":
            create_assistant()
        elif sys.argv[1] == "--delete-assistant":
            if len(sys.argv) != 3:
                print("Please provide the assistant ID to delete")
                print("Usage: python main.py --delete-assistant <assistant_id>")
                sys.exit(1)
            delete_assistant(sys.argv[2])
        elif sys.argv[1] == "--test-message":
            if len(sys.argv) != 4:
                print("Please provide both thread ID and message")
                print("Usage: python main.py --test-message <thread_id> <message>")
                sys.exit(1)
            test_message(sys.argv[2], sys.argv[3])
        else:
            print("Unknown command. Available commands:")
            print("  --generate-thread")
            print("  --create-assistant")
            print("  --delete-assistant <assistant_id>")
            print("  --test-message <thread_id> <message>")
    else:
        main()
