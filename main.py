import asyncio
import logging
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


def initialize_tools():
    """Initialize and register all tools"""
    weather_tool = WeatherTool(settings.OPENWEATHER_API_KEY)
    active_clients_tool = KMCActiveClientsTool()
    available_offices_tool = KMCAvailableOfficesTool()

    registry.register(weather_tool)
    registry.register(active_clients_tool)
    registry.register(available_offices_tool)

    return registry.get_function_definitions()


def run_conversation(
    message: str,
    channel: str = "weather-update",
):
    """Run the main conversation loop

    Args:
        message (str): The user's message to start the conversation
        channel (str): The WebSocket channel to use for communication
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

    except Exception as e:
        logger.error(f"Error in conversation: {str(e)}")
    finally:
        # Cleanup
        if "assistant" in locals():
            openai_service.delete_assistant(assistant.id)
        if loop:
            loop.run_until_complete(websocket_service.disconnect())
            loop.close()


if __name__ == "__main__":
    # Example usage
    sample_message = (
        "How many active clients does KMC currently have? Per service type?"
    )

    run_conversation(message=sample_message)
