# AI Instructions for Cosmo - KMC Solutions Assistant

## Project Overview

Cosmo is a specialized professional assistant for KMC Solutions that combines weather expertise, business analytics, and office space consulting. The project uses OpenAI's Assistant API with WebSocket integration for real-time updates and follows a service-based architecture pattern.

## Architecture Overview

The project follows a modular, service-based architecture:

1. **Services Layer** (`app/services/`):
   - `openai_service.py`: Manages OpenAI assistant interactions
   - `websocket_service.py`: Handles multi-channel WebSocket communications

2. **Tools Layer** (`app/tools/`):
   - `weather.py`: Weather information functionality
   - `kmc_active_clients.py`: Client analytics functionality
   - `kmc_available_offices.py`: Office space availability functionality
   - `registry.py`: Tool registration and management
   - `base.py`: Base classes and interfaces

3. **Handlers Layer** (`app/handlers/`):
   - `event_handler.py`: Manages event processing and tool execution

4. **Core Layer** (`app/core/`):
   - `config.py`: Application configuration and settings

## Core Principles

1. **Professional Identity**:
   - Cosmo is a valued member of the KMC Solutions team
   - Weather queries: Channel Kuya Kim's friendly, expert style
   - Business/Sales queries: Maintain professional, consultative tone
   - Always maintain appropriate persona per query type

2. **Service-Based Communication**:
   - All responses streamed via WebSocket
   - Channel-specific message handling
   - Proper subscription management
   - Comprehensive error handling

3. **Code Structure**:
   - Service-oriented architecture
   - Clear separation of concerns
   - Modular tool implementation
   - Centralized configuration

## Service Development Guidelines

1. **OpenAI Service**:
   ```python
   class OpenAIService:
       def create_assistant(self, function_definitions):
           # Assistant creation and management
       
       def stream_conversation(self, thread_id, assistant_id, event_handler):
           # Conversation streaming
   ```

2. **WebSocket Service**:
   ```python
   class WebSocketService:
       def subscribe(self, channel: str):
           # Channel subscription
       
       def send_message(self, channel: str, message_data: Dict):
           # Channel-specific message sending
   ```

3. **Event Handler**:
   ```python
   class CosmoEventHandler:
       def on_event(self, event):
           # Event processing
       
       def handle_tool_calls(self, data):
           # Tool execution management
   ```

## Tool Development Guidelines

1. **Naming Conventions**:
   - Use specific, focused file names (e.g., `kmc_active_clients.py`)
   - Class names should match file purpose (e.g., `KMCActiveClientsTool`)
   - Include descriptive suffixes (e.g., Tool, Service)

2. **Tool Structure**:
   ```python
   class YourSpecificTool(BaseAssistantTool):
       def get_function_definition(self):
           # Function definition for OpenAI
       
       async def your_specific_function(self):
           # Tool implementation
   ```

## Communication Patterns

1. **WebSocket Messages**:
   ```json
   {
       "channel": "channel-name",
       "payload": {
           "message": "content",
           "timestamp": 1234567890,
           "status": "in_progress|completed|error",
           "type": "response|error|tool"
       }
   }
   ```

2. **Channel Management**:
   - Each functionality has its own channel
   - Weather updates: "weather-update"
   - Business analytics: "business-update"
   - Sales/Office space: "sales-update"

## Error Handling

1. **Service Level**:
   - Connection management
   - Channel subscription errors
   - Message delivery failures
   - Service cleanup

2. **Tool Level**:
   - Function execution errors
   - Data validation
   - Resource management
   - Error reporting

## Best Practices

1. **Service Development**:
   - Follow single responsibility principle
   - Implement proper error handling
   - Use async/await patterns
   - Maintain service independence

2. **Tool Implementation**:
   - Clear function definitions
   - Comprehensive error handling
   - Proper resource cleanup
   - Detailed logging

3. **Event Processing**:
   - Handle all event types
   - Maintain message order
   - Proper error propagation
   - Clean state management

## Current Tools

1. **Weather Information**:
   - File: `weather.py`
   - Class: `WeatherTool`
   - Channel: "weather-update"
   - Purpose: Weather updates with Kuya Kim's personality

2. **KMC Client Analytics**:
   - File: `kmc_active_clients.py`
   - Class: `KMCActiveClientsTool`
   - Channel: "business-update"
   - Purpose: Client portfolio analysis

3. **Office Space Availability**:
   - File: `kmc_available_offices.py`
   - Class: `KMCAvailableOfficesTool`
   - Channel: "sales-update"
   - Purpose: Office space consulting

## Usage Example

```python
# Initialize and run conversation
run_conversation(
    message="What's the weather like in Makati?",
    channel="weather-update"
)

# Business analytics query
run_conversation(
    message="How many active clients do we have?",
    channel="business-update"
)

# Office space query
run_conversation(
    message="Show available spaces in BGC for 50 people",
    channel="sales-update"
)
```

## Prohibited Actions

1. DO NOT:
   - Mix service responsibilities
   - Skip channel management
   - Ignore error handling
   - Leave connections unclosed
   - Mix tool personalities
   - Hardcode credentials
   - Use generic service names
   - Skip proper cleanup
   - Bypass WebSocket channels
   - Ignore documentation updates

Remember: This project serves as a critical interface for KMC Solutions. Maintain high standards for code quality, security, and user experience. Follow the service-based architecture and ensure proper separation of concerns. 