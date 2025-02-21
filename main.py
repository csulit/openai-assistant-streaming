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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RabbitMQ Configuration
RABBITMQ_URL = settings.RABBITMQ_URL
QUEUE_NAME = settings.QUEUE_NAME
ROUTING_KEY = settings.ROUTING_KEY
EXCHANGE_NAME = settings.EXCHANGE_NAME


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
    channel: str = "weather-update",
) -> bool:
    """Run the main conversation loop

    Args:
        message (str): The user's message to start the conversation
        channel (str): The WebSocket channel to use for communication

    Returns:
        bool: True if conversation completed successfully, False otherwise
    """
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
        loop.run_until_complete(websocket_service.connect())
        loop.run_until_complete(websocket_service.subscribe(channel))

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
            thread_id=thread.id, assistant_id=assistant.id, event_handler=event_handler
        )

        return True

    except Exception as e:
        logger.error(f"Error in conversation: {str(e)}")
        return False
    finally:
        # Cleanup
        if "assistant" in locals():
            openai_service.delete_assistant(assistant.id)
        if loop:
            loop.run_until_complete(websocket_service.disconnect())
            loop.close()


def process_message(message_data: dict) -> bool:
    """Process a message from RabbitMQ

    Args:
        message_data (dict): The message data from RabbitMQ

    Returns:
        bool: True if processed successfully, False otherwise
    """
    try:
        # Extract required fields from message_data
        user_message = message_data.get("message")
        channel = message_data.get("channel", "weather-update")

        if not user_message:
            logger.error("No message found in RabbitMQ data")
            return False

        # Run the conversation
        return run_conversation(message=user_message, channel=channel)

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return False


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
                        message_data = json.loads(body)
                        if process_message(message_data):
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                        else:
                            ch.basic_nack(
                                delivery_tag=method.delivery_tag, requeue=True
                            )
                except TimeoutError:
                    logger.warning("⌛ Processing timed out, requeuing")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            # Set up consumer
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=queue_name, on_message_callback=callback, auto_ack=False
            )

            logger.info("[*] Waiting for messages...")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError:
            logger.error("Connection lost, reconnecting...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Consumer stopped")
            break
        finally:
            if connection and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
