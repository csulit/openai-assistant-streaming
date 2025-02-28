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
from app.services.redis_service import RedisService

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

# Initialize Redis service
redis_service = RedisService()

tools = [
    weather_tool,
    active_clients_tool,
    available_offices_tool,
    user_audit_tool,
    user_role_tool,
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
    message_id: str,
    properties=None,
) -> tuple[bool, str]:
    """Run the main conversation loop

    Args:
        message (str): The user's message to start the conversation
        channel (str): The channel UUID for WebSocket communication
        message_id (str): The message ID for the conversation
        properties: RabbitMQ message properties for potential reply handling

    Returns:
        tuple[bool, str]: (success, error_message)
        - success: True if conversation completed successfully
        - error_message: Description of error if any, empty string if successful
    """
    # Get assistant ID from Redis
    assistant_id = redis_service.get_assistant_id()

    if not assistant_id:
        error_msg = "No assistant ID found in Redis. Please create an assistant first using --create-assistant"
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

            # Initialize event handler with both services, channel, and message_id
            event_handler = CosmoEventHandler(
                websocket_service, openai_service, channel, loop, message_id
            )

            try:
                # Get thread ID from Redis or create a new one
                thread_id = redis_service.get_thread_id(channel)

                # If no thread ID exists for this channel, create a new thread
                if not thread_id:
                    logger.info(
                        f"No existing thread found for channel {channel}, creating new thread"
                    )
                    thread = openai_service.create_thread()
                    thread_id = thread.id
                    # Store the new thread ID in Redis
                    redis_service.set_thread_id(channel, thread_id)
                    # Initialize metadata
                    redis_service.set_thread_metadata(
                        channel,
                        {
                            "created_at": time.time(),
                            "message_count": 0,
                            "last_message_at": time.time(),
                        },
                    )
                else:
                    logger.info(
                        f"Using existing thread {thread_id} for channel {channel}"
                    )
                    # Check if thread exists in OpenAI
                    thread_exists, error = openai_service.check_thread_exists(thread_id)
                    if not thread_exists:
                        logger.warning(
                            f"Thread {thread_id} not found in OpenAI, creating new thread"
                        )
                        thread = openai_service.create_thread()
                        thread_id = thread.id
                        # Update Redis with new thread ID
                        redis_service.set_thread_id(channel, thread_id)

                # Update metadata
                metadata = redis_service.get_thread_metadata(channel)
                metadata["message_count"] = metadata.get("message_count", 0) + 1
                metadata["last_message_at"] = time.time()
                redis_service.set_thread_metadata(channel, metadata)

                # Recreate event handler with thread_id
                event_handler = CosmoEventHandler(
                    websocket_service,
                    openai_service,
                    channel,
                    loop,
                    message_id,
                    thread_id,
                )

                # Create message with user's input using the thread_id
                message_obj = openai_service.create_message(
                    thread_id, message, event_handler=event_handler
                )
                logger.info(f"Created message: {message_obj.id}")

                # Start conversation stream
                logger.info("Starting conversation stream...")
                openai_service.stream_conversation(
                    thread_id=thread_id,
                    assistant_id=assistant_id,
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
                            "message_id": message_id,
                            "thread_id": thread_id,
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
                            "message_id": message_id,
                            "thread_id": thread_id,
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
                # Delete the thread mapping from Redis
                redis_service.delete_thread(channel)
                error_message = {
                    "message": error_msg,
                    "timestamp": time.time(),
                    "status": "error",
                    "type": "error",
                    "error_details": str(e),
                    "message_id": message_id,
                    "thread_id": thread_id,
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
                    "message_id": message_id,
                    "thread_id": thread_id,
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
                    "message_id": message_id,
                    "thread_id": thread_id,
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
            error_msg = "Invalid 'channel' field - must be a string identifier (UUID, Convex ID, or any unique string)"
            logger.error(error_msg)
            return False, False, error_msg

        # Validate message_id (now required)
        message_id = message_data.get("message_id")
        if not message_id:
            error_msg = "Missing required 'message_id' field"
            logger.error(error_msg)
            return False, False, error_msg

        if not isinstance(message_id, str):
            error_msg = "Invalid 'message_id' field"
            logger.error(error_msg)
            return False, False, error_msg

        # Run the conversation
        conversation_success, error_msg = run_conversation(
            message=user_message,
            channel=channel,
            message_id=message_id,
            properties=properties,
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
    """Create a new assistant and get its ID, or retrieve existing ID from Redis"""
    # First check if we already have an assistant ID in Redis
    existing_assistant_id = redis_service.get_assistant_id()

    if existing_assistant_id:
        print(f"\n=== USING EXISTING ASSISTANT ===")
        print(f"Assistant ID: {existing_assistant_id}")
        print(f"=================================\n")

        # Verify the assistant exists in OpenAI
        openai_service = OpenAIService()
        try:
            # Try to retrieve the assistant to verify it exists
            assistant = openai_service.client.beta.assistants.retrieve(
                existing_assistant_id
            )
            print(f"Verified assistant exists: {assistant.name}")
            return existing_assistant_id
        except Exception as e:
            print(f"Error retrieving existing assistant: {str(e)}")
            print("Creating a new assistant instead...")
            # Continue to create a new assistant

    # Create a new assistant
    openai_service = OpenAIService()
    assistant_id = openai_service.create_assistant_id(
        registry.get_function_definitions()
    )

    # Store the new assistant ID in Redis
    if assistant_id:
        success = redis_service.set_assistant_id(assistant_id)
        if success:
            print(f"Assistant ID stored in Redis successfully")
        else:
            print(f"Failed to store assistant ID in Redis")

    return assistant_id


def delete_assistant(assistant_id: str):
    """Delete an assistant by ID and remove from Redis if it matches the stored ID"""
    openai_service = OpenAIService()
    openai_service.delete_assistant(assistant_id)

    # Check if this is the assistant ID stored in Redis
    stored_id = redis_service.get_assistant_id()
    if stored_id == assistant_id:
        # Remove the assistant ID from Redis using the proper method
        success = redis_service.delete_assistant_id()
        if success:
            print(f"Assistant ID removed from Redis")
        else:
            print(f"Failed to remove assistant ID from Redis")
    else:
        print(f"Note: Deleted assistant was not the one stored in Redis")


def clear_all_threads():
    """Clear all thread IDs and metadata from Redis

    This command will delete all channel-to-thread mappings and their associated metadata
    from Redis, effectively resetting all conversations. The assistant ID will remain intact.

    Use with caution as this operation cannot be undone.
    """
    if not redis_service.redis:
        print("Redis not available, cannot clear threads")
        return False

    try:
        # Get all keys with the thread prefix
        thread_pattern = f"{redis_service.prefix}thread:*"
        metadata_pattern = f"{redis_service.prefix}metadata:*"

        # Get all keys matching the patterns
        thread_keys = redis_service.redis.keys(thread_pattern)
        metadata_keys = redis_service.redis.keys(metadata_pattern)

        # Count the keys
        thread_count = len(thread_keys)
        metadata_count = len(metadata_keys)

        # Show warning and ask for confirmation
        print(f"\n=== WARNING: REDIS CLEANUP ===")
        print(f"You are about to delete:")
        print(f"- {thread_count} thread mappings")
        print(f"- {metadata_count} metadata entries")
        print(f"")
        print(f"This will reset all conversations but keep the assistant ID.")
        print(f"This operation CANNOT be undone.")
        print(f"============================\n")

        confirmation = input("Type 'DELETE' to confirm: ")
        if confirmation != "DELETE":
            print("Operation cancelled.")
            return False

        # Delete all keys
        if thread_keys:
            redis_service.redis.delete(*thread_keys)
        if metadata_keys:
            redis_service.redis.delete(*metadata_keys)

        print(f"\n=== REDIS CLEANUP COMPLETE ===")
        print(f"Deleted {thread_count} thread mappings")
        print(f"Deleted {metadata_count} metadata entries")
        print(f"==============================\n")

        return True
    except Exception as e:
        print(f"\n=== ERROR CLEARING THREADS ===")
        print(f"Error: {str(e)}")
        print(f"==============================\n")
        return False


def clear_old_threads(days: int):
    """Clear thread IDs and metadata from Redis that are older than the specified number of days

    Args:
        days (int): Delete threads older than this many days

    This command will delete channel-to-thread mappings and their associated metadata
    from Redis that haven't been accessed in the specified number of days.
    The assistant ID will remain intact.

    Use with caution as this operation cannot be undone.
    """
    if not redis_service.redis:
        print("Redis not available, cannot clear threads")
        return False

    if days <= 0:
        print("Days must be a positive number")
        return False

    try:
        # Get all keys with the thread prefix
        thread_pattern = f"{redis_service.prefix}thread:*"
        metadata_pattern = f"{redis_service.prefix}metadata:*"

        # Get all keys matching the patterns
        thread_keys = redis_service.redis.keys(thread_pattern)
        metadata_keys = redis_service.redis.keys(metadata_pattern)

        # Get current time
        current_time = time.time()
        # Convert days to seconds
        cutoff_seconds = days * 24 * 60 * 60

        # Find old threads based on metadata
        old_thread_channels = []
        for metadata_key in metadata_keys:
            try:
                # Get the channel ID from the metadata key
                channel_id = metadata_key.decode("utf-8").replace(
                    f"{redis_service.prefix}metadata:", ""
                )

                # Get the metadata
                metadata_json = redis_service.redis.get(metadata_key)
                if metadata_json:
                    metadata = json.loads(metadata_json.decode("utf-8"))
                    last_message_time = metadata.get("last_message_at", 0)

                    # Check if the thread is older than the cutoff
                    if current_time - last_message_time > cutoff_seconds:
                        old_thread_channels.append(channel_id)
            except Exception as e:
                print(f"Error processing metadata key {metadata_key}: {str(e)}")

        # Count old threads
        old_thread_count = len(old_thread_channels)

        # Show warning and ask for confirmation
        print(f"\n=== WARNING: REDIS CLEANUP (OLDER THAN {days} DAYS) ===")
        print(f"You are about to delete:")
        print(f"- {old_thread_count} thread mappings and their metadata")
        print(f"")
        print(
            f"This will remove conversations that haven't been accessed in {days} days."
        )
        print(f"This operation CANNOT be undone.")
        print(f"================================================\n")

        confirmation = input("Type 'DELETE' to confirm: ")
        if confirmation != "DELETE":
            print("Operation cancelled.")
            return False

        # Delete old threads
        deleted_thread_count = 0
        deleted_metadata_count = 0

        for channel_id in old_thread_channels:
            thread_key = f"{redis_service.prefix}thread:{channel_id}"
            metadata_key = f"{redis_service.prefix}metadata:{channel_id}"

            # Delete thread key
            if redis_service.redis.exists(thread_key):
                redis_service.redis.delete(thread_key)
                deleted_thread_count += 1

            # Delete metadata key
            if redis_service.redis.exists(metadata_key):
                redis_service.redis.delete(metadata_key)
                deleted_metadata_count += 1

        print(f"\n=== REDIS CLEANUP COMPLETE ===")
        print(f"Deleted {deleted_thread_count} thread mappings")
        print(f"Deleted {deleted_metadata_count} metadata entries")
        print(f"All were older than {days} days")
        print(f"==============================\n")

        return True
    except Exception as e:
        print(f"\n=== ERROR CLEARING OLD THREADS ===")
        print(f"Error: {str(e)}")
        print(f"=================================\n")
        return False


def show_thread_stats():
    """Show statistics about threads stored in Redis

    This command displays information about:
    - Total number of threads
    - Age distribution (how many threads in different age ranges)
    - Total storage used
    - Oldest and newest threads
    """
    if not redis_service.redis:
        print("Redis not available, cannot show thread statistics")
        return False

    try:
        # Get all keys with the thread prefix
        thread_pattern = f"{redis_service.prefix}thread:*"
        metadata_pattern = f"{redis_service.prefix}metadata:*"

        # Get all keys matching the patterns
        thread_keys = redis_service.redis.keys(thread_pattern)
        metadata_keys = redis_service.redis.keys(metadata_pattern)

        # Count the keys
        thread_count = len(thread_keys)
        metadata_count = len(metadata_keys)

        # Get current time
        current_time = time.time()

        # Age distribution buckets (in days)
        age_buckets = {
            "0-1 days": 0,
            "1-7 days": 0,
            "7-30 days": 0,
            "30-90 days": 0,
            "90+ days": 0,
        }

        # Track oldest and newest
        oldest_time = current_time
        newest_time = 0
        oldest_channel = None
        newest_channel = None

        # Message count stats
        total_messages = 0
        max_messages = 0
        max_messages_channel = None

        # Analyze metadata
        for metadata_key in metadata_keys:
            try:
                # Get the channel ID from the metadata key
                channel_id = metadata_key.decode("utf-8").replace(
                    f"{redis_service.prefix}metadata:", ""
                )

                # Get the metadata
                metadata_json = redis_service.redis.get(metadata_key)
                if metadata_json:
                    metadata = json.loads(metadata_json.decode("utf-8"))
                    last_message_time = metadata.get("last_message_at", 0)
                    created_at = metadata.get("created_at", last_message_time)
                    message_count = metadata.get("message_count", 0)

                    # Update message stats
                    total_messages += message_count
                    if message_count > max_messages:
                        max_messages = message_count
                        max_messages_channel = channel_id

                    # Calculate age in days
                    age_days = (current_time - last_message_time) / (24 * 60 * 60)

                    # Update age distribution
                    if age_days <= 1:
                        age_buckets["0-1 days"] += 1
                    elif age_days <= 7:
                        age_buckets["1-7 days"] += 1
                    elif age_days <= 30:
                        age_buckets["7-30 days"] += 1
                    elif age_days <= 90:
                        age_buckets["30-90 days"] += 1
                    else:
                        age_buckets["90+ days"] += 1

                    # Update oldest/newest
                    if last_message_time < oldest_time:
                        oldest_time = last_message_time
                        oldest_channel = channel_id
                    if last_message_time > newest_time:
                        newest_time = last_message_time
                        newest_channel = channel_id
            except Exception as e:
                print(f"Error processing metadata key {metadata_key}: {str(e)}")

        # Calculate average messages per thread
        avg_messages = total_messages / thread_count if thread_count > 0 else 0

        # Calculate storage used (approximate)
        storage_used = 0
        for key in thread_keys + metadata_keys:
            try:
                value = redis_service.redis.get(key)
                if value:
                    storage_used += len(key) + len(value)
            except:
                pass

        # Convert to KB
        storage_kb = storage_used / 1024

        # Print statistics
        print(f"\n=== REDIS THREAD STATISTICS ===")
        print(f"Total threads: {thread_count}")
        print(f"Total metadata entries: {metadata_count}")
        print(f"")
        print(f"Age distribution:")
        for bucket, count in age_buckets.items():
            print(
                f"  {bucket}: {count} threads ({count/thread_count*100:.1f}% of total)"
                if thread_count > 0
                else f"  {bucket}: 0 threads (0.0% of total)"
            )
        print(f"")
        print(f"Message statistics:")
        print(f"  Total messages: {total_messages}")
        print(f"  Average messages per thread: {avg_messages:.1f}")
        print(
            f"  Most active thread: {max_messages} messages (channel: {max_messages_channel})"
        )
        print(f"")
        print(f"Time statistics:")
        if oldest_channel:
            oldest_date = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(oldest_time)
            )
            print(f"  Oldest thread: {oldest_date} (channel: {oldest_channel})")
        if newest_channel:
            newest_date = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(newest_time)
            )
            print(f"  Newest thread: {newest_date} (channel: {newest_channel})")
        print(f"")
        print(f"Storage statistics:")
        print(f"  Approximate storage used: {storage_kb:.2f} KB")
        print(f"===============================\n")

        return True
    except Exception as e:
        print(f"\n=== ERROR SHOWING THREAD STATISTICS ===")
        print(f"Error: {str(e)}")
        print(f"=======================================\n")
        return False


def test_message(channel_id: str, message: str):
    """Test sending a message directly to a channel

    Args:
        channel_id (str): The channel identifier (UUID, Convex ID, or any unique string) that maps to an OpenAI thread in Redis
        message (str): The message to send
    """
    try:
        # Create event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Generate a test message_id
        message_id = f"test_msg_{uuid.uuid4().hex[:8]}"
        print(f"Using test message_id: {message_id}")
        print(f"Using channel ID: {channel_id}")
        print(
            "Note: Channel ID is used to look up or create an OpenAI thread ID in Redis"
        )

        # Get assistant ID from Redis
        assistant_id = redis_service.get_assistant_id()

        if not assistant_id:
            print("No assistant ID found in Redis. Creating a new assistant...")
            assistant_id = create_assistant()
            if not assistant_id:
                print("Failed to create assistant, exiting")
                sys.exit(1)
        else:
            print(f"Using assistant ID: {assistant_id}")

        # Initialize services
        openai_service = OpenAIService()
        websocket_service = WebSocketService()

        # Connect to WebSocket
        loop.run_until_complete(websocket_service.connect())
        loop.run_until_complete(websocket_service.subscribe(channel_id))

        # Get or create thread ID from Redis
        openai_thread_id = redis_service.get_thread_id(channel_id)

        if not openai_thread_id:
            print(
                f"No existing thread found for channel {channel_id}, creating new thread"
            )
            thread = openai_service.create_thread()
            openai_thread_id = thread.id
            # Store the new thread ID in Redis
            redis_service.set_thread_id(channel_id, openai_thread_id)
            # Initialize metadata
            redis_service.set_thread_metadata(
                channel_id,
                {
                    "created_at": time.time(),
                    "message_count": 0,
                    "last_message_at": time.time(),
                },
            )
        else:
            print(f"Using existing thread {openai_thread_id} for channel {channel_id}")
            # Check if thread exists in OpenAI
            thread_exists, error = openai_service.check_thread_exists(openai_thread_id)
            if not thread_exists:
                print(
                    f"Thread {openai_thread_id} not found in OpenAI, creating new thread"
                )
                thread = openai_service.create_thread()
                openai_thread_id = thread.id
                # Update Redis with new thread ID
                redis_service.set_thread_id(channel_id, openai_thread_id)

        # Update metadata
        metadata = redis_service.get_thread_metadata(channel_id)
        metadata["message_count"] = metadata.get("message_count", 0) + 1
        metadata["last_message_at"] = time.time()
        redis_service.set_thread_metadata(channel_id, metadata)

        # Initialize event handler with thread_id
        event_handler = CosmoEventHandler(
            websocket_service,
            openai_service,
            channel_id,
            loop,
            message_id,
            openai_thread_id,  # Pass the thread_id to the event handler
        )

        # Create and process message
        openai_service.create_message(
            openai_thread_id, message, event_handler=event_handler
        )
        openai_service.stream_conversation(
            thread_id=openai_thread_id,
            assistant_id=assistant_id,
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
                # Wait a moment to ensure all messages are sent
                time.sleep(1)
                print("\nConversation completed successfully!")
                break

            time.sleep(0.1)

    except Exception as e:
        print(f"\n=== ERROR ===\n{str(e)}\n============")
        sys.exit(1)
    finally:
        # Clean up
        try:
            if websocket_service and loop:
                loop.run_until_complete(websocket_service.disconnect())
                loop.close()
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")
        sys.exit(0)


def generate_uuid():
    """Generate and display a channel identifier for testing purposes, and create a thread ID in Redis

    Note: For production use with Convex, you can use Convex IDs instead of UUIDs as channel identifiers.
    """
    # Generate UUID
    generated_uuid = str(uuid.uuid4())

    # Create a thread in OpenAI
    openai_service = OpenAIService()
    thread = openai_service.create_thread()
    thread_id = thread.id

    # Store the thread ID in Redis
    redis_service.set_thread_id(generated_uuid, thread_id)

    # Initialize metadata
    redis_service.set_thread_metadata(
        generated_uuid,
        {
            "created_at": time.time(),
            "message_count": 0,
            "last_message_at": time.time(),
        },
    )

    print(f"\n=== GENERATED CHANNEL IDENTIFIER ===")
    print(f"Channel ID: {generated_uuid}")
    print(f"Thread ID: {thread_id}")
    print(f"===================================\n")
    print(f"Use this channel ID with the test-message command:")
    print(f'python main.py --test-message {generated_uuid} "Your test message"')
    print(
        f"\nNote: For production use with Convex, you can use Convex IDs instead of UUIDs."
    )

    return generated_uuid


def main():
    """Main RabbitMQ consumer loop"""
    # Generate a unique consumer tag for this worker instance
    consumer_tag = f"cosmo_worker_{uuid.uuid4().hex[:8]}"

    # Check if we have an assistant ID in Redis
    assistant_id = redis_service.get_assistant_id()

    # If no assistant ID is found, create a new one
    if not assistant_id:
        logger.info("No assistant ID found in Redis, creating a new assistant")
        assistant_id = create_assistant()
        if not assistant_id:
            logger.error("Failed to create assistant, exiting")
            return
    else:
        logger.info(f"Using existing assistant ID: {assistant_id}")

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

                        # Extract message_id for error reporting
                        message_id = message_data.get("message_id")
                        channel = message_data.get("channel")

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
                                websocket_service.subscribe(channel)
                            )

                            error_message = {
                                "message": error_msg,
                                "timestamp": time.time(),
                                "status": "error",
                                "type": "error",
                                "error_details": error_msg,
                                "message_id": message_id,
                                "thread_id": (
                                    thread_id if "thread_id" in locals() else None
                                ),
                            }
                            error_loop.run_until_complete(
                                websocket_service.send_message(channel, error_message)
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
                            # Extract message_id and channel for error reporting
                            message_id = message_data.get("message_id")
                            channel = message_data.get("channel")

                            # Send timeout error via WebSocket
                            error_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(error_loop)
                            websocket_service = WebSocketService()
                            error_loop.run_until_complete(websocket_service.connect())
                            error_loop.run_until_complete(
                                websocket_service.subscribe(channel)
                            )

                            error_message = {
                                "message": error_msg,
                                "timestamp": time.time(),
                                "status": "error",
                                "type": "timeout",
                                "error_details": "Processing exceeded 90 second timeout limit",
                                "message_id": message_id,
                                "thread_id": (
                                    thread_id if "thread_id" in locals() else None
                                ),
                            }
                            error_loop.run_until_complete(
                                websocket_service.send_message(channel, error_message)
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
                            # Extract message_id and channel for error reporting
                            message_id = message_data.get("message_id")
                            channel = message_data.get("channel")

                            # Send error via WebSocket
                            error_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(error_loop)
                            websocket_service = WebSocketService()
                            error_loop.run_until_complete(websocket_service.connect())
                            error_loop.run_until_complete(
                                websocket_service.subscribe(channel)
                            )

                            error_message = {
                                "message": error_msg,
                                "timestamp": time.time(),
                                "status": "error",
                                "type": "error",
                                "error_details": str(e),
                                "message_id": message_id,
                                "thread_id": (
                                    thread_id if "thread_id" in locals() else None
                                ),
                            }
                            error_loop.run_until_complete(
                                websocket_service.send_message(channel, error_message)
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
        elif sys.argv[1] == "--generate-uuid":
            generate_uuid()
        elif sys.argv[1] == "--test-message":
            if len(sys.argv) != 4:
                print("Please provide both channel ID and message")
                print("Usage: python main.py --test-message <channel_id> <message>")
                sys.exit(1)
            test_message(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "--clear-all-threads":
            clear_all_threads()
        elif sys.argv[1] == "--clear-old-threads":
            if len(sys.argv) != 3:
                print("Please provide the number of days")
                print("Usage: python main.py --clear-old-threads <days>")
                sys.exit(1)
            clear_old_threads(int(sys.argv[2]))
        elif sys.argv[1] == "--show-thread-stats":
            show_thread_stats()
        else:
            print("Unknown command. Available commands:")
            print("  --generate-thread")
            print("  --create-assistant")
            print("  --delete-assistant <assistant_id>")
            print("  --generate-uuid")
            print("  --test-message <channel_id> <message>")
            print("  --clear-all-threads")
            print("  --clear-old-threads <days>")
            print("  --show-thread-stats")
    else:
        main()
