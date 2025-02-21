from typing import Dict, Any
import pyodbc
import logging
from ..core.config import settings
from .base import BaseAssistantTool

logger = logging.getLogger(__name__)


class KMCAvailableOfficesTool(BaseAssistantTool):
    """Tool for finding available office spaces in KMC buildings based on location and capacity requirements"""

    def __init__(self):
        logger.info("Initializing KMCAvailableOfficesTool")
        self.connection_string = settings.MSSQL_CONNECTION_STRING
        # Test connection on initialization
        try:
            with pyodbc.connect(self.connection_string) as conn:
                logger.info("Successfully connected to MSSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to MSSQL database: {str(e)}")
            raise ValueError("Database connection failed")

    @property
    def name(self) -> str:
        return "get_available_offices"

    def get_function_definition(self) -> Dict[str, Any]:
        """Get OpenAI function definition"""
        return {
            "name": self.name,
            "description": "Find available office spaces in KMC buildings based on city location and required capacity. This will help identify suitable office spaces for potential clients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The city where to search for available offices (e.g., 'Makati', 'Taguig', 'BGC')",
                    },
                    "capacity": {
                        "type": "integer",
                        "description": "The required seating capacity for the office space",
                    },
                },
                "required": ["city", "capacity"],
            },
        }

    async def get_available_offices(self, city: str, capacity: int) -> Dict[str, Any]:
        """Get available office spaces based on location and capacity"""
        logger.info(f"Querying available offices in {city} with capacity of {capacity}")

        try:
            with pyodbc.connect(self.connection_string) as conn:
                cursor = conn.cursor()

                # Execute stored procedure with parameters
                cursor.execute(
                    "EXEC sp_GetAvailableOffices @City = ?, @Capacity = ?",
                    (city, capacity),
                )

                # Convert the results to a list of dictionaries
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))

                # Format the response
                response = {
                    "total_available_spaces": len(results),
                    "city": city,
                    "required_capacity": capacity,
                    "available_offices": results,
                }

                logger.info(
                    f"Successfully retrieved available offices. Found {len(results)} spaces in {city}"
                )
                return response

        except pyodbc.Error as e:
            logger.error(
                f"Database error occurred while fetching available offices: {str(e)}"
            )
            raise ValueError(f"Database query failed: {str(e)}")
        except Exception as e:
            logger.error(
                f"Unexpected error in get_available_offices: {str(e)}", exc_info=True
            )
            raise ValueError(f"Error getting available office data: {str(e)}")
