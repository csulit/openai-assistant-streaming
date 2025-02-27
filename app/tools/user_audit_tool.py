from typing import Dict, Any, List
from .base import BaseAssistantTool
from collections import Counter
from datetime import datetime
import aiohttp
import logging
from urllib.parse import quote
from ..core.config import settings

logger = logging.getLogger(__name__)

class UserAuditTool(BaseAssistantTool):
    """Tool for retrieving and analyzing user audit logs"""

    def __init__(self):
        self.base_url = settings.AUDIT_API_URL.rstrip('/')
        self.api_key = settings.X_API_KEY
        if not self.api_key:
            raise ValueError("X_API_KEY setting is not configured")

    @property
    def name(self) -> str:
        return "get_user_audit_logs"

    def get_function_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": "Retrieve and analyze audit logs for a specific user, providing activity history and insights",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Email address of the user to get audit logs for"
                    }
                },
                "required": ["email"]
            }
        }

    async def analyze_audit_logs(self, logs: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze audit logs to provide insights"""
        items = logs['items']
        
        # Initialize counters and data structures
        action_counts = Counter()
        table_counts = Counter()
        change_types = Counter()
        activity_hours = Counter()
        
        for item in items:
            # Count actions (create, update, delete)
            action_counts[item['action']] += 1
            
            # Count affected tables
            if item['tableName']:
                table_counts[item['tableName']] += 1
            
            # Analyze change types from changeSummary
            change_types[item['changeSummary']] += 1
            
            # Track activity patterns by hour
            created_at = datetime.strptime(item['createdAt'], "%Y-%m-%d %H:%M:%S.%f")
            activity_hours[created_at.hour] += 1

        # Generate insights
        insights = {
            "total_activities": len(items),
            "most_common_actions": dict(action_counts.most_common(3)),
            "most_affected_tables": dict(table_counts.most_common(3)),
            "common_change_types": dict(change_types.most_common(3)),
            "peak_activity_hours": dict(activity_hours.most_common(3)),
            "recent_activity": bool(items and (datetime.now() - datetime.strptime(items[0]['createdAt'], "%Y-%m-%d %H:%M:%S.%f")).days < 7)
        }

        return insights

    async def get_user_audit_logs(self, email: str) -> Dict[str, Any]:
        """
        Retrieve and analyze audit logs for a specific user
        
        Args:
            email (str): Email address of the user
            
        Returns:
            Dict containing audit logs and insights
        """
        try:
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key
            }
            
            # URL encode the email and construct the full URL
            encoded_email = quote(email)
            url = f"{self.base_url}/{encoded_email}"
            
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

                    audit_data = data['data']
                    
                    # Generate insights from the audit data
                    insights = await self.analyze_audit_logs(audit_data)
                    
                    return {
                        "audit_logs": {
                            "items": audit_data['items'],
                            "pagination": {
                                "totalPages": audit_data['totalPages'],
                                "totalCount": audit_data['totalCount'],
                                "hasPreviousPage": audit_data['hasPreviousPage'],
                                "hasNextPage": audit_data['hasNextPage']
                            }
                        },
                        "insights": insights,
                        "summary": {
                            "email": email,
                            "total_records": audit_data['totalCount'],
                            "date_range": {
                                "from": audit_data['items'][-1]['createdAt'] if audit_data['items'] else None,
                                "to": audit_data['items'][0]['createdAt'] if audit_data['items'] else None
                            }
                        }
                    }
            
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching audit logs: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching audit logs for {email}: {str(e)}")
            raise 