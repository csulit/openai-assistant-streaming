# AI Instructions for KMC Assistant Project

## Project Overview

This is a specialized AI assistant project for KMC Solutions that combines weather information and sales analytics. The project uses OpenAI's Assistant API with WebSocket integration for real-time updates and follows a strict architectural pattern.

## Core Principles

1. **Dual Personality Maintenance**:
   - Weather queries: Maintain Kuya Kim's friendly, humorous personality
   - Sales queries: Maintain professional, analytical tone
   - Never mix personalities between functions

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

1. **Base Structure**:
   ```python
   from typing import Dict, Any
   from .base import BaseAssistantTool

   class YourTool(BaseAssistantTool):
       @property
       def name(self) -> str:
           return "your_function_name"

       def get_function_definition(self) -> Dict[str, Any]:
           # Must include comprehensive description and parameters
           pass

       async def your_function_name(self) -> Dict[str, Any]:
           # Must include proper error handling and logging
           pass
   ```

2. **Error Handling Requirements**:
   - Use try-except blocks for all external operations
   - Include comprehensive logging
   - Propagate errors with meaningful messages
   - Send error notifications via WebSocket

3. **Configuration Management**:
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

2. **Query Safety**:
   - Use parameterized queries
   - Implement query timeout
   - Handle large result sets appropriately
   - Format results consistently

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

## Testing Guidelines

Before submitting changes:

1. **Connection Testing**:
   - Test WebSocket connectivity
   - Verify database connections
   - Check API integrations

2. **Error Handling**:
   - Test error scenarios
   - Verify error messages
   - Check WebSocket error propagation

3. **Response Format**:
   - Verify message format consistency
   - Check status updates
   - Validate timestamps

## Security Considerations

1. **Environment Variables**:
   - Never hardcode sensitive data
   - Use settings for configuration
   - Update .env.example with new variables

2. **Data Protection**:
   - Sanitize database inputs
   - Validate API responses
   - Handle sensitive data appropriately

## Performance Guidelines

1. **Async Operations**:
   - Use async/await for I/O operations
   - Implement proper error handling
   - Maintain connection pools

2. **Resource Management**:
   - Clean up connections
   - Handle memory efficiently
   - Implement timeouts

## Response Formatting

1. **Weather Responses**:
   - Include temperature, humidity, wind speed
   - Add Kuya Kim's personality
   - Include weather-appropriate jokes

2. **Sales Responses**:
   - Format numbers consistently
   - Provide clear summaries
   - Maintain professional tone

## Maintenance Rules

1. **Version Control**:
   - Update requirements.txt with new dependencies
   - Maintain consistent versioning
   - Document breaking changes

2. **Configuration Updates**:
   - Add new settings to config.py
   - Update environment variable documentation
   - Maintain backward compatibility

## Best Practices Checklist

Before implementing changes:

- [ ] Does it follow the modular architecture?
- [ ] Are all configurations in settings?
- [ ] Is proper error handling implemented?
- [ ] Are WebSocket messages properly formatted?
- [ ] Is documentation updated?
- [ ] Are security considerations addressed?
- [ ] Is proper logging implemented?
- [ ] Are tests included?
- [ ] Is the personality maintained?
- [ ] Are resource cleanups implemented?

## Prohibited Actions

1. DO NOT:
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

Remember: This project serves as a critical interface for KMC Solutions. Maintain high standards for code quality, security, and user experience. 