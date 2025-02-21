import json
import time
import asyncio
import websockets
import logging
from typing import Dict, Any, Optional, Set
from ..core.config import settings

logger = logging.getLogger(__name__)


class WebSocketService:
    def __init__(self, uri: str = settings.WEBSOCKET_URI):
        self.uri = uri
        self.websocket = None
        self.subscribed_channels: Set[str] = set()
        self.loop = None
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        self.subscription_timeout = 5  # seconds

    def set_loop(self, loop):
        """Set the event loop for async operations"""
        self.loop = loop

    async def connect(self):
        """Connect to the WebSocket server"""
        retries = 0
        while retries < self.max_retries:
            try:
                self.websocket = await websockets.connect(self.uri)
                logger.info("Successfully connected to WebSocket server")
                return
            except Exception as e:
                retries += 1
                if retries == self.max_retries:
                    logger.error(
                        f"Failed to connect after {self.max_retries} attempts: {str(e)}"
                    )
                    self.websocket = None
                    raise
                logger.warning(
                    f"Connection attempt {retries} failed, retrying in {self.retry_delay} seconds..."
                )
                await asyncio.sleep(self.retry_delay)

    async def subscribe(self, channel: str):
        """Subscribe to a specific channel with retries"""
        if not self.websocket:
            raise ValueError("WebSocket not connected")

        try:
            # Exactly match the required subscription format
            subscribe_message = {
                "channel": "subscription",
                "payload": {"action": "subscribe", "channel": channel},
            }
            await self.websocket.send(json.dumps(subscribe_message))

            # Add to subscribed channels immediately
            # The server logs show it accepts subscriptions right away
            self.subscribed_channels.add(channel)
            logger.info(f"Successfully subscribed to channel: {channel}")
            return

        except Exception as e:
            logger.error(f"Error subscribing to channel {channel}: {str(e)}")
            raise

    async def unsubscribe(self, channel: str):
        """Unsubscribe from a specific channel"""
        if not self.websocket or channel not in self.subscribed_channels:
            return

        try:
            # Exactly match the required unsubscription format
            unsubscribe_message = {
                "channel": "subscription",
                "payload": {"action": "unsubscribe", "channel": channel},
            }
            await self.websocket.send(json.dumps(unsubscribe_message))

            # Remove from subscribed channels immediately
            self.subscribed_channels.discard(channel)
            logger.info(f"Unsubscribed from channel: {channel}")

        except Exception as e:
            logger.error(f"Error unsubscribing from channel {channel}: {str(e)}")
            # Still remove from our tracked channels even if send fails
            self.subscribed_channels.discard(channel)

    async def send_message(self, channel: str, message_data: Dict[str, Any]):
        """Send a message to a specific channel with retries"""
        if not self.websocket:
            raise ValueError("WebSocket not connected")

        if channel not in self.subscribed_channels:
            raise ValueError(f"Not subscribed to channel: {channel}")

        retries = 0
        while retries < self.max_retries:
            try:
                # Exactly match the required broadcast format
                message = {"channel": channel, "payload": message_data}
                await self.websocket.send(json.dumps(message))
                logger.debug(f"Message sent successfully to channel: {channel}")
                return
            except Exception as e:
                retries += 1
                if retries == self.max_retries:
                    logger.error(
                        f"Failed to send message after {self.max_retries} attempts: {str(e)}"
                    )
                    raise
                logger.warning(
                    f"Send attempt {retries} failed, retrying in {self.retry_delay} seconds..."
                )
                await asyncio.sleep(self.retry_delay)

    async def send_error(
        self, channel: str, error: Exception, friendly_message: Optional[str] = None
    ):
        """Send an error message to a specific channel"""
        error_message = {
            "message": friendly_message
            or "An error occurred while processing your request.",
            "error": str(error),
            "timestamp": time.time(),
            "status": "error",
            "type": "error",
        }
        await self.send_message(channel, error_message)

    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        if self.websocket:
            try:
                # Unsubscribe from all channels without waiting for confirmation
                for channel in list(self.subscribed_channels):
                    try:
                        unsubscribe_message = {
                            "channel": "subscription",
                            "payload": {"action": "unsubscribe", "channel": channel},
                        }
                        await self.websocket.send(json.dumps(unsubscribe_message))
                    except Exception as e:
                        logger.warning(
                            f"Failed to send unsubscribe message for channel {channel}: {str(e)}"
                        )

                # Clear all subscribed channels
                self.subscribed_channels.clear()

                # Close the connection
                await self.websocket.close()
                self.websocket = None
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error during WebSocket disconnect: {str(e)}")
                # Ensure websocket is marked as closed even if there's an error
                self.websocket = None
