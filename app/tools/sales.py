from typing import Dict, Any
import pyodbc
import logging
from ..core.config import settings
from .base import BaseAssistantTool

logger = logging.getLogger(__name__)

class SalesTool(BaseAssistantTool):
    """Tool for getting sales and client information"""
    
    def __init__(self):
        logger.info("Initializing SalesTool")
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
        return "get_client_count"

    def get_function_definition(self) -> Dict[str, Any]:
        """Get OpenAI function definition"""
        return {
            "name": self.name,
            "description": "Get the count of active clients per service type from KMC's database",
            "parameters": {
                "type": "object",
                "properties": {},  # No parameters needed as the query is fixed
                "required": []
            }
        }

    async def get_client_count(self) -> Dict[str, Any]:
        """Get client count per service type"""
        logger.info("Querying client count per service")
        
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
                    "total_clients": sum(row['ClientCount'] for row in results),
                    "services": results
                }
                
                logger.info("Successfully retrieved client count data")
                return response
                
        except pyodbc.Error as e:
            logger.error(f"Database error occurred: {str(e)}")
            raise ValueError(f"Database query failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in get_client_count: {str(e)}", exc_info=True)
            raise ValueError(f"Error getting client count: {str(e)}") 