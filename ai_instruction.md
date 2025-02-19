# AI Instructions for Cosmo - KMC Solutions Assistant

## Project Overview

Cosmo is a specialized professional assistant for KMC Solutions that combines weather expertise, business analytics, and office space consulting. The project uses OpenAI's Assistant API with WebSocket integration for real-time updates and follows a strict architectural pattern.

## Core Principles

1. **Professional Identity**:
   - Cosmo is a valued member of the KMC Solutions team
   - Weather queries: Channel Kuya Kim's friendly, expert style
   - Business/Sales queries: Maintain professional, consultative tone
   - Always maintain appropriate persona per query type

2. **Real-time Communication**:
   - All responses must be streamed via WebSocket
   - Follow established message format and protocols
   - Maintain proper error handling and status updates

3. **Code Structure**:
   - Follow modular architecture
   - Maintain separation of concerns
   - Keep configuration in settings

## Tool Development Guidelines

When creating or modifying tools:

1. **Naming Conventions**:
   - Use specific, focused file names (e.g., `kmc_active_clients.py`)
   - Avoid generic names (e.g., 'sales.py', 'utils.py')
   - Class names should match file purpose (e.g., `KMCActiveClientsTool`)
   - Include descriptive suffixes (e.g., Tool, Service)
   - Examples:
     ```
     ✅ Good:
     - kmc_active_clients.py → KMCActiveClientsTool
     - weather.py → WeatherTool
     
     ❌ Bad:
     - sales.py → SalesTool
     - business.py → BusinessTool
     ```

2. **Base Structure**:
   ```python
   from typing import Dict, Any
   from .base import BaseAssistantTool

   class YourSpecificTool(BaseAssistantTool):
       """Tool for specific functionality - provide clear description"""
       
       @property
       def name(self) -> str:
           return "your_specific_function_name"

       def get_function_definition(self) -> Dict[str, Any]:
           # Must include comprehensive description and parameters
           pass

       async def your_specific_function_name(self) -> Dict[str, Any]:
           # Must include proper error handling and logging
           pass
   ```

3. **Error Handling Requirements**:
   - Use try-except blocks for all external operations
   - Include comprehensive logging
   - Propagate errors with meaningful messages
   - Send error notifications via WebSocket
   - Handle database/API errors appropriately

4. **Configuration Management**:
   - Add new settings to `app/core/config.py`
   - Use environment variables for sensitive data
   - Include default values where appropriate
   - Update README with new environment variables

## WebSocket Communication

All messages must follow this format:

```json
{
    "type": "channel-name",
    "payload": {
        "message": "content",
        "timestamp": 1234567890,
        "status": "in_progress|completed|error",
        "type": "response|error"
    }
}
```

## Database Operations

When working with database tools:

1. **Connection Management**:
   - Use connection pooling
   - Implement proper connection cleanup
   - Handle connection timeouts
   - Log connection issues
   - Test connections on initialization

2. **Query Safety**:
   - Use parameterized queries
   - Implement query timeout
   - Handle large result sets appropriately
   - Format results consistently
   - Include proper error handling

## Documentation Requirements

When modifying the project:

1. **Code Documentation**:
   - Add docstrings to all functions
   - Include type hints
   - Document parameters and return values
   - Add usage examples

2. **Update Relevant MD Files**:
   - `README.md` for new features or dependencies
   - `contributing.md` for new development patterns
   - `websocket.md` for WebSocket changes
   - `main.py.md` for core functionality changes
   - `ai_instruction.md` for AI behavior changes

## Response Formatting

1. **Weather Responses**:
   - Include temperature, humidity, wind speed
   - Add Kuya Kim's personality
   - Include weather-appropriate jokes

2. **Business Analytics Responses**:
   - Format numbers consistently
   - Provide clear summaries
   - Maintain professional tone
   - Include relevant context
   - Present data in a structured format

## Best Practices Checklist

Before implementing changes:

- [ ] Does it follow the modular architecture?
- [ ] Does the tool name follow naming conventions?
- [ ] Are all configurations in settings?
- [ ] Is proper error handling implemented?
- [ ] Are WebSocket messages properly formatted?
- [ ] Is documentation updated?
- [ ] Are security considerations addressed?
- [ ] Is proper logging implemented?
- [ ] Are tests included?
- [ ] Is the personality maintained?
- [ ] Are resource cleanups implemented?
- [ ] Are database operations properly handled?

## Prohibited Actions

1. DO NOT:
   - Use generic tool names
   - Mix tool personalities
   - Hardcode credentials
   - Skip error handling
   - Bypass WebSocket manager
   - Ignore documentation updates
   - Leave connections unclosed
   - Remove existing error checks
   - Change message formats
   - Skip logging
   - Modify core architecture
   - Use non-descriptive variable names

## Current Tools

1. **Weather Information**:
   - File: `weather.py`
   - Class: `WeatherTool`
   - Purpose: Provide weather information with Kuya Kim's personality

2. **KMC Client Analytics**:
   - File: `kmc_active_clients.py`
   - Class: `KMCActiveClientsTool`
   - Purpose: Provide active client counts per service type

Remember: This project serves as a critical interface for KMC Solutions. Maintain high standards for code quality, security, and user experience. Follow the naming conventions strictly and ensure proper separation of concerns. 