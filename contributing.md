# Contributing to the AI Assistant

This guide will help you extend the AI assistant's capabilities by adding new functions. The assistant uses a tool-based architecture where each tool represents a specific functionality that can be invoked by the AI.

## Architecture Overview

The project uses a modular architecture with the following key components:

- `app/tools/base.py`: Contains the base classes and protocols for creating tools
- `app/tools/registry.py`: Manages tool registration and execution
- `app/tools/weather.py`: Weather information functionality
- `app/tools/kmc_active_clients.py`: KMC client analytics functionality
- `main.py`: Initializes the OpenAI assistant and handles the conversation flow

## Tool Naming Conventions

1. **Specific and Focused**:
   - Use clear, specific names for tool files
   - Name should reflect exact functionality
   - Avoid generic names (e.g., 'sales.py', 'utils.py')
   - Examples: 
     - ✅ `kmc_active_clients.py`
     - ✅ `weather.py`
     - ❌ `sales.py`
     - ❌ `business.py`

2. **Class Naming**:
   - Class name should match file purpose
   - Include descriptive suffix (e.g., Tool, Service)
   - Examples:
     - `KMCActiveClientsTool`
     - `WeatherTool`

## Creating a New Tool

### 1. Create a New Tool Class

Create a new Python file in the `app/tools` directory. Your tool should inherit from `BaseAssistantTool` and implement the required methods.

Example structure:

```python
from typing import Dict, Any
from .base import BaseAssistantTool

class YourSpecificTool(BaseAssistantTool):
    """Tool for specific functionality - provide clear description"""
    
    def __init__(self):
        # Initialize your tool
        pass

    @property
    def name(self) -> str:
        # Return the function name that will be used by the AI
        return "your_specific_function_name"

    def get_function_definition(self) -> Dict[str, Any]:
        # Define the OpenAI function schema
        return {
            "name": self.name,
            "description": "Detailed description of what your function does",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "Description of parameter 1"
                    },
                    # Add more parameters as needed
                },
                "required": ["param1"]  # List required parameters
            }
        }

    async def your_specific_function_name(self, param1: str) -> Dict[str, Any]:
        # Implement your function logic
        # The function name must match the name property
        result = await self._process(param1)
        return result
```

### 2. Register Your Tool

In `main.py`, register your tool with the registry:

```python
from app.tools.your_specific_tool import YourSpecificTool

# Initialize your tool
your_tool = YourSpecificTool()

# Register it with the registry
registry.register(your_tool)
```

## Best Practices

1. **Error Handling**:
   - Implement comprehensive error handling in your tool
   - Use logging to track execution
   - Return meaningful error messages
   - Handle database/API errors appropriately

2. **Async Support**:
   - Implement functions as async when they involve I/O operations
   - Use `httpx` for HTTP requests instead of `requests`
   - Handle database operations asynchronously when possible

3. **Type Hints**:
   - Use proper type hints for all methods
   - Document parameter types in the function definition
   - Use descriptive type names

4. **Documentation**:
   - Provide clear descriptions in your function definition
   - Document parameters thoroughly
   - Include examples in docstrings
   - Update relevant MD files

## Example Implementation

Here's a simplified version of the KMCActiveClientsTool as an example:

```python
from typing import Dict, Any
import pyodbc
import logging
from ..core.config import settings
from .base import BaseAssistantTool

class KMCActiveClientsTool(BaseAssistantTool):
    """Tool for getting KMC's active client information per service type"""
    
    def __init__(self):
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
        return {
            "name": self.name,
            "description": "Get the count of active clients per service type",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

    async def get_active_clients_per_service(self) -> Dict[str, Any]:
        try:
            with pyodbc.connect(self.connection_string) as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM vw_ClientCountPerService ORDER BY ClientCount DESC"
                cursor.execute(query)
                
                # Format results
                response = {
                    "total_active_clients": sum(row['ClientCount'] for row in results),
                    "service_breakdown": results
                }
                return response
                
        except Exception as e:
            logger.error(f"Error in get_active_clients_per_service: {str(e)}")
            raise ValueError(f"Error getting client data: {str(e)}")
```

## Testing Your Tool

1. Create test cases for your tool
2. Test error handling
3. Test with the AI assistant
4. Monitor the logs for proper execution
5. Verify WebSocket messages

## Security Considerations

1. Never hardcode sensitive information
2. Use environment variables for configuration
3. Validate and sanitize input parameters
4. Implement rate limiting if necessary
5. Handle sensitive data appropriately
6. Use proper database connection management

## Need Help?

If you need assistance or have questions about implementing a new tool:

1. Check existing tools in the `app/tools` directory for examples
2. Review the OpenAI function calling documentation
3. Open an issue for discussion

Remember to update the requirements.txt file if your tool requires new dependencies.
