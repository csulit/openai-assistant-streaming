import redis
import logging
import json
from typing import Optional, Dict, Any
from ..core.config import settings

logger = logging.getLogger(__name__)


class RedisService:
    """Service for Redis operations, primarily for mapping channel identifiers to thread IDs"""

    def __init__(self):
        """Initialize Redis connection"""
        try:
            self.redis = redis.from_url(settings.REDIS_URL)
            self.prefix = settings.REDIS_PREFIX
            self.expiry = (
                settings.REDIS_THREAD_EXPIRY
            )  # Default: 90 days (7,776,000 seconds)
            logger.info(f"Connected to Redis at {settings.REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            self.redis = None

    def _get_thread_key(self, channel_id: str) -> str:
        """Get the Redis key for a thread mapping"""
        return f"{self.prefix}thread:{channel_id}"

    def _get_metadata_key(self, channel_id: str) -> str:
        """Get the Redis key for thread metadata"""
        return f"{self.prefix}metadata:{channel_id}"

    def get_thread_id(self, channel_id: str) -> Optional[str]:
        """Get thread ID for a channel

        Args:
            channel_id (str): The channel identifier (UUID, Convex ID, or any unique string)

        Returns:
            Optional[str]: The OpenAI thread ID or None if not found
        """
        if not self.redis:
            logger.warning("Redis not available, using channel as thread ID")
            return channel_id

        try:
            thread_id = self.redis.get(self._get_thread_key(channel_id))
            if thread_id:
                # Refresh expiry on access
                self.redis.expire(self._get_thread_key(channel_id), self.expiry)
                self.redis.expire(self._get_metadata_key(channel_id), self.expiry)
                return thread_id.decode("utf-8")
            return None
        except Exception as e:
            logger.error(f"Error retrieving thread ID from Redis: {str(e)}")
            return None

    def set_thread_id(self, channel_id: str, thread_id: str) -> bool:
        """Set thread ID for a channel

        Args:
            channel_id (str): The channel identifier (UUID, Convex ID, or any unique string)
            thread_id (str): The OpenAI thread ID

        Returns:
            bool: True if successful, False otherwise

        Note:
            The mapping will automatically expire after 90 days of inactivity.
            Each access to the thread ID refreshes the expiry timer.
        """
        if not self.redis:
            logger.warning("Redis not available, cannot store thread mapping")
            return False

        try:
            # Store the thread ID with expiry
            self.redis.setex(self._get_thread_key(channel_id), self.expiry, thread_id)
            logger.info(f"Mapped channel {channel_id} to thread {thread_id}")
            return True
        except Exception as e:
            logger.error(f"Error storing thread ID in Redis: {str(e)}")
            return False

    def get_thread_metadata(self, channel_id: str) -> Dict[str, Any]:
        """Get metadata for a thread

        Args:
            channel_id (str): The channel identifier (UUID, Convex ID, or any unique string)

        Returns:
            Dict[str, Any]: Thread metadata or empty dict if not found
        """
        if not self.redis:
            logger.warning("Redis not available, cannot retrieve metadata")
            return {}

        try:
            metadata = self.redis.get(self._get_metadata_key(channel_id))
            if metadata:
                # Refresh expiry on access
                self.redis.expire(self._get_metadata_key(channel_id), self.expiry)
                return json.loads(metadata.decode("utf-8"))
            return {}
        except Exception as e:
            logger.error(f"Error retrieving thread metadata from Redis: {str(e)}")
            return {}

    def set_thread_metadata(self, channel_id: str, metadata: Dict[str, Any]) -> bool:
        """Set metadata for a thread

        Args:
            channel_id (str): The channel identifier (UUID, Convex ID, or any unique string)
            metadata (Dict[str, Any]): Thread metadata

        Returns:
            bool: True if successful, False otherwise

        Note:
            The metadata will automatically expire after 90 days of inactivity.
            Each access to the thread metadata refreshes the expiry timer.
        """
        if not self.redis:
            logger.warning("Redis not available, cannot store metadata")
            return False

        try:
            # Store the metadata with expiry
            self.redis.setex(
                self._get_metadata_key(channel_id), self.expiry, json.dumps(metadata)
            )
            logger.info(f"Updated metadata for channel {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Error storing thread metadata in Redis: {str(e)}")
            return False

    def delete_thread(self, channel_id: str) -> bool:
        """Delete thread mapping and metadata

        Args:
            channel_id (str): The channel identifier (UUID, Convex ID, or any unique string)

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.redis:
            logger.warning("Redis not available, cannot delete thread")
            return False

        try:
            # Delete both thread ID and metadata
            self.redis.delete(
                self._get_thread_key(channel_id), self._get_metadata_key(channel_id)
            )
            logger.info(f"Deleted thread mapping for channel {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting thread from Redis: {str(e)}")
            return False

    def _get_assistant_key(self) -> str:
        """Get the Redis key for the assistant ID"""
        return f"{self.prefix}assistant_id"

    def get_assistant_id(self) -> Optional[str]:
        """Get the OpenAI assistant ID from Redis

        Returns:
            Optional[str]: The OpenAI assistant ID or None if not found
        """
        if not self.redis:
            logger.warning("Redis not available, cannot retrieve assistant ID")
            return None

        try:
            assistant_id = self.redis.get(self._get_assistant_key())
            if assistant_id:
                return assistant_id.decode("utf-8")
            return None
        except Exception as e:
            logger.error(f"Error retrieving assistant ID from Redis: {str(e)}")
            return None

    def set_assistant_id(self, assistant_id: str) -> bool:
        """Set the OpenAI assistant ID in Redis

        Args:
            assistant_id (str): The OpenAI assistant ID

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.redis:
            logger.warning("Redis not available, cannot store assistant ID")
            return False

        try:
            # Store the assistant ID permanently (no expiry)
            self.redis.set(self._get_assistant_key(), assistant_id)
            logger.info(f"Stored assistant ID {assistant_id} in Redis")
            return True
        except Exception as e:
            logger.error(f"Error storing assistant ID in Redis: {str(e)}")
            return False

    def has_assistant_id(self) -> bool:
        """Check if an assistant ID exists in Redis

        Returns:
            bool: True if an assistant ID exists, False otherwise
        """
        return self.get_assistant_id() is not None

    def delete_assistant_id(self) -> bool:
        """Delete the OpenAI assistant ID from Redis

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.redis:
            logger.warning("Redis not available, cannot delete assistant ID")
            return False

        try:
            self.redis.delete(self._get_assistant_key())
            logger.info("Deleted assistant ID from Redis")
            return True
        except Exception as e:
            logger.error(f"Error deleting assistant ID from Redis: {str(e)}")
            return False
