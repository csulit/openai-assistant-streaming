from typing import Dict, Any
from .base import BaseAssistantTool
import aiohttp
import logging
from urllib.parse import quote
from ..core.config import settings

logger = logging.getLogger(__name__)

class UserRoleTool(BaseAssistantTool):
    """Tool for retrieving user role information"""

    def __init__(self):
        self.base_url = settings.USER_ROLE_API_URL.rstrip('/')
        self.api_key = settings.X_API_KEY
        if not self.api_key:
            raise ValueError("X_API_KEY setting is not configured")

    @property
    def name(self) -> str:
        return "get_user_role"

    def get_function_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": "Retrieve role information for a specific user",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Email address of the user to get role information for"
                    }
                },
                "required": ["email"]
            }
        }

    async def get_user_role(self, email: str) -> Dict[str, Any]:
        """
        Retrieve role information for a specific user
        
        Args:
            email (str): Email address of the user
            
        Returns:
            Dict containing user role information
        """
        try:
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key
            }
            
            # URL encode the email and construct the full URL
            encoded_email = quote(email)
            url = f"{self.base_url}/{encoded_email}/role"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API request failed: {error_text}")
                        raise Exception(f"API request failed with status {response.status}: {error_text}")
                    
                    data = await response.json()
                    if 'data' not in data:
                        logger.error(f"Unexpected API response format: {data}")
                        raise Exception("API response does not contain 'data' field")

                    return {
                        "user_role": data['data'],
                        "email": email
                    }
            
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching user role: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching role for {email}: {str(e)}")
            raise 