from typing import Dict, Any, List
from .base import AssistantTool
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def singleton(cls):
    """Singleton decorator"""
    instances = {}
    
    @wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

@singleton
class AssistantToolRegistry:
    """Registry for assistant tools"""
    
    def __init__(self):
        self._tools: Dict[str, AssistantTool] = {}
    
    def register(self, tool: AssistantTool) -> None:
        """Register a tool"""
        logger.info(f"Registering tool: {tool.name}")
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} already registered. Overwriting.")
        self._tools[tool.name] = tool
    
    def unregister(self, tool_name: str) -> None:
        """Unregister a tool"""
        if tool_name in self._tools:
            logger.info(f"Unregistering tool: {tool_name}")
            del self._tools[tool_name]
        else:
            logger.warning(f"Attempted to unregister non-existent tool: {tool_name}")
    
    def get_tool(self, name: str) -> AssistantTool:
        """Get a tool by name"""
        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")
        return self._tools[name]
    
    def get_function_definitions(self) -> List[Dict[str, Any]]:
        """Get all function definitions for OpenAI"""
        return [tool.get_function_definition() for tool in self._tools.values()]
    
    async def execute_function(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a function by name with given arguments"""
        tool = self.get_tool(name)
        method = getattr(tool, name)
        return await method(**arguments)
    
    @property
    def tools(self) -> Dict[str, AssistantTool]:
        """Get all registered tools"""
        return self._tools.copy()

# Global registry instance
registry = AssistantToolRegistry() 