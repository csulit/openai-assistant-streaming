from typing import Dict, Any
import pyodbc
import logging
from ..core.config import settings
from .base import BaseAssistantTool

logger = logging.getLogger(__name__)

class KMCActiveClientsTool(BaseAssistantTool):
    """Tool for getting KMC's active client information per service type"""
    
    def __init__(self):
        logger.info("Initializing KMCActiveClientsTool")
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
        return "get_active_clients_per_service"

    def get_function_definition(self) -> Dict[str, Any]:
        """Get OpenAI function definition"""
        return {
            "name": self.name,
            "description": "Get the count of active clients per service type from KMC's database. This will show how many active clients KMC currently has for each service offering.",
            "parameters": {
                "type": "object",
                "properties": {},  # No parameters needed as the query is fixed
                "required": []
            }
        }

    async def get_active_clients_per_service(self) -> Dict[str, Any]:
        """Get active client count per service type"""
        logger.info("Querying active client count per service type")
        
        try:
            with pyodbc.connect(self.connection_string) as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM vw_ClientCountPerService ORDER BY ClientCount DESC"
                cursor.execute(query)
                
                # Convert the results to a list of dictionaries
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                # Format the response
                response = {
                    "total_active_clients": sum(row['ClientCount'] for row in results),
                    "service_breakdown": results
                }
                
                logger.info(f"Successfully retrieved active client data. Total clients: {response['total_active_clients']}")
                return response
                
        except pyodbc.Error as e:
            logger.error(f"Database error occurred while fetching active clients: {str(e)}")
            raise ValueError(f"Database query failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in get_active_clients_per_service: {str(e)}", exc_info=True)
            raise ValueError(f"Error getting active client data: {str(e)}") 