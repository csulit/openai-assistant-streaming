# Contributing to the AI Assistant

This guide will help you extend the AI assistant's capabilities by adding new functions. The assistant uses a tool-based architecture where each tool represents a specific functionality that can be invoked by the AI.

## Architecture Overview

The project uses a modular architecture with the following key components:

- `app/tools/base.py`: Contains the base classes and protocols for creating tools
- `app/tools/registry.py`: Manages tool registration and execution
- `main.py`: Initializes the OpenAI assistant and handles the conversation flow

## Creating a New Tool

### 1. Create a New Tool Class

Create a new Python file in the `app/tools` directory. Your tool should inherit from `BaseAssistantTool` and implement the required methods.

Example structure:

```python
from typing import Dict, Any
from .base import BaseAssistantTool

class YourTool(BaseAssistantTool):
    def __init__(self):
        # Initialize your tool
        pass

    @property
    def name(self) -> str:
        # Return the function name that will be used by the AI
        return "your_function_name"

    def get_function_definition(self) -> Dict[str, Any]:
        # Define the OpenAI function schema
        return {
            "name": self.name,
            "description": "Description of what your function does",
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

    async def your_function_name(self, param1: str) -> Dict[str, Any]:
        # Implement your function logic
        # The function name must match the name property
        result = await self._process(param1)
        return result
```

### 2. Register Your Tool

In `main.py`, register your tool with the registry:

```python
from app.tools.your_tool import YourTool

# Initialize your tool
your_tool = YourTool()

# Register it with the registry
registry.register(your_tool)
```

## Best Practices

1. **Error Handling**:
   - Implement comprehensive error handling in your tool
   - Use logging to track execution
   - Return meaningful error messages

2. **Async Support**:
   - Implement functions as async when they involve I/O operations
   - Use `httpx` for HTTP requests instead of `requests`

3. **Type Hints**:
   - Use proper type hints for all methods
   - Document parameter types in the function definition

4. **Documentation**:
   - Provide clear descriptions in your function definition
   - Document parameters thoroughly
   - Include examples in docstrings

## Example Implementation

Here's a simplified version of the WeatherTool as an example:

```python
from typing import Dict, Any
import httpx
from .base import BaseAssistantTool

class WeatherTool(BaseAssistantTool):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"

    @property
    def name(self) -> str:
        return "get_weather"

    def get_function_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": "Get current weather information for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name (e.g., 'London')"
                    }
                },
                "required": ["city"]
            }
        }

    async def get_weather(self, city: str) -> Dict[str, Any]:
        try:
            params = {
                "q": city,
                "appid": self.api_key,
                "units": "metric"
            }
            async with httpx.AsyncClient() as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            raise ValueError(f"Error getting weather data: {str(e)}")
```

## Testing Your Tool

1. Create test cases for your tool
2. Test error handling
3. Test with the AI assistant by asking questions that would trigger your tool
4. Monitor the logs for proper execution

## Security Considerations

1. Never hardcode sensitive information (API keys, credentials)
2. Use environment variables for configuration
3. Validate and sanitize input parameters
4. Implement rate limiting if necessary
5. Handle sensitive data appropriately

## Need Help?

If you need assistance or have questions about implementing a new tool:

1. Check existing tools in the `app/tools` directory for examples
2. Review the OpenAI function calling documentation
3. Open an issue for discussion

Remember to update the requirements.txt file if your tool requires new dependencies.
