from .registry import registry
from .base import BaseAssistantTool
from .weather import WeatherTool
from .user_audit_tool import UserAuditTool
from .user_role_tool import UserRoleTool

# Register all tools
def register_tools():
    """Register all available tools"""
    registry.register(UserAuditTool())
    registry.register(UserRoleTool())

# Initialize tools
register_tools()

__all__ = [
    "registry",
    "BaseAssistantTool",
    "WeatherTool",
    "UserAuditTool",
    "UserRoleTool"
] 