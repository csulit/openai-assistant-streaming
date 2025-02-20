from typing import Dict, Any
import httpx
from geopy.geocoders import Nominatim
import logging
from ..core.config import settings
from .base import BaseAssistantTool

logger = logging.getLogger(__name__)


class WeatherTool(BaseAssistantTool):
    """Tool for getting weather information"""

    def __init__(self, api_key: str):
        logger.info("Initializing WeatherTool")
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        self.geocoder = Nominatim(user_agent="assistant_weather_app")
        if not api_key:
            logger.error("Weather API key not provided")
            raise ValueError("Weather API key is required")

    @property
    def name(self) -> str:
        return "get_weather"

    def get_function_definition(self) -> Dict[str, Any]:
        """Get OpenAI function definition"""
        return {
            "name": self.name,
            "description": "Get current weather information for a city. The function will automatically convert city names to coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name (e.g., 'London', 'New York', 'Tokyo')",
                    },
                    "country_code": {
                        "type": "string",
                        "description": "Optional: Two-letter country code for better accuracy (e.g., 'GB', 'US', 'JP')",
                        "pattern": "^[A-Z]{2}$",
                    },
                },
                "required": ["city"],
            },
        }

    async def get_weather(self, city: str, country_code: str = None) -> Dict[str, Any]:
        """Get current weather for a location"""
        logger.info(f"Getting weather for city: {city}, country_code: {country_code}")

        try:
            # Get coordinates from city name
            location_query = f"{city}, {country_code}" if country_code else city
            logger.debug(f"Geocoding location: {location_query}")
            location = self.geocoder.geocode(location_query)

            if not location:
                logger.error(
                    f"Could not find coordinates for location: {location_query}"
                )
                raise ValueError(f"Could not find coordinates for {location_query}")

            logger.debug(
                f"Found coordinates: lat={location.latitude}, lon={location.longitude}"
            )
            params = {
                "lat": location.latitude,
                "lon": location.longitude,
                "appid": self.api_key,
                "units": "metric",
                "exclude": "minutely,hourly,daily,alerts",
            }

            async with httpx.AsyncClient() as client:
                logger.debug(f"Making API request to: {self.base_url}")
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()

                # Format the response for better readability
                weather_info = {
                    "temperature": data["main"]["temp"],
                    "feels_like": data["main"]["feels_like"],
                    "humidity": data["main"]["humidity"],
                    "description": data["weather"][0]["description"],
                    "wind_speed": data["wind"]["speed"],
                    "location": {
                        "name": data["name"],
                        "country": data["sys"]["country"],
                    },
                }

                logger.info(f"Successfully retrieved weather data for {location_query}")
                return weather_info

        except httpx.HTTPError as e:
            logger.error(f"HTTP error occurred while fetching weather: {str(e)}")
            logger.error(
                f"Response status: {e.response.status_code if hasattr(e, 'response') else 'N/A'}"
            )
            logger.error(
                f"Response body: {e.response.text if hasattr(e, 'response') else 'N/A'}"
            )
            raise ValueError(f"Failed to fetch weather data: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in get_weather: {str(e)}", exc_info=True)
            raise ValueError(f"Error getting weather data: {str(e)}")
