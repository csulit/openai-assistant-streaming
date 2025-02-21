import json
import time
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

    def set_loop(self, loop):
        """Set the event loop for async operations"""
        self.loop = loop

    async def connect(self):
        """Connect to the WebSocket server"""
        try:
            self.websocket = await websockets.connect(self.uri)
            logger.info("Successfully connected to WebSocket server")
        except Exception as e:
            logger.error(f"Error connecting to WebSocket: {str(e)}")
            self.websocket = None
            raise

    async def subscribe(self, channel: str):
        """Subscribe to a specific channel"""
        if not self.websocket:
            raise ValueError("WebSocket not connected")

        try:
            subscribe_message = {"type": "subscribe", "payload": {"channel": channel}}
            await self.websocket.send(json.dumps(subscribe_message))

            # Wait for subscription confirmation
            response = await self.websocket.recv()
            response_data = json.loads(response)

            if response_data.get("type") == "subscribed":
                self.subscribed_channels.add(channel)
                logger.info(f"Successfully subscribed to channel: {channel}")
            else:
                logger.error(f"Failed to subscribe to channel: {channel}")
                raise ValueError(f"Failed to subscribe to channel: {channel}")

        except Exception as e:
            logger.error(f"Error subscribing to channel {channel}: {str(e)}")
            raise

    async def unsubscribe(self, channel: str):
        """Unsubscribe from a specific channel"""
        if not self.websocket or channel not in self.subscribed_channels:
            return

        try:
            unsubscribe_message = {
                "type": "unsubscribe",
                "payload": {"channel": channel},
            }
            await self.websocket.send(json.dumps(unsubscribe_message))

            # Remove from subscribed channels immediately
            self.subscribed_channels.remove(channel)
            logger.info(f"Unsubscribed from channel: {channel}")

        except Exception as e:
            logger.error(f"Error unsubscribing from channel {channel}: {str(e)}")
            # Still remove from our tracked channels even if send fails
            self.subscribed_channels.discard(channel)

    async def send_message(self, channel: str, message_data: Dict[str, Any]):
        """Send a message to a specific channel"""
        if not self.websocket:
            raise ValueError("WebSocket not connected")

        if channel not in self.subscribed_channels:
            raise ValueError(f"Not subscribed to channel: {channel}")

        try:
            message = {"type": channel, "payload": message_data}
            logger.debug(f"Sending message to channel {channel}: {json.dumps(message)}")
            await self.websocket.send(json.dumps(message))
            logger.debug(f"Message sent successfully to channel: {channel}")
        except Exception as e:
            logger.error(f"Error sending message to channel {channel}: {str(e)}")
            raise

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
                            "type": "unsubscribe",
                            "payload": {"channel": channel},
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
