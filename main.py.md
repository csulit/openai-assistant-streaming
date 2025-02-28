# Main Application Documentation

## Overview

The `main.py` file serves as the core of our AI assistant application. It integrates OpenAI's Assistant API with various tools and services, using WebSocket for real-time communication, RabbitMQ for message queuing, and Redis for conversation persistence.

## Core Components

### 1. Configuration and Initialization

```python
# OpenAI Configuration
openai_service = OpenAIService()

# Tool Registration
weather_tool = WeatherTool(settings.OPENWEATHER_API_KEY)
active_clients_tool = KMCActiveClientsTool()
available_offices_tool = KMCAvailableOfficesTool()
user_audit_tool = UserAuditTool()
user_role_tool = UserRoleTool()

registry.register(weather_tool)
registry.register(active_clients_tool)
registry.register(available_offices_tool)
registry.register(user_audit_tool)
registry.register(user_role_tool)

# Redis Service
redis_service = RedisService()
```

The application initializes with:
- OpenAI service configuration
- Tool registration for various functionalities
- WebSocket service setup
- Redis service for conversation persistence

### 2. Assistant Management

```python
def create_assistant():
    # Check for existing assistant ID in Redis
    existing_assistant_id = redis_service.get_assistant_id()
    
    if existing_assistant_id:
        # Verify the assistant exists in OpenAI
        # Return existing ID if valid
    
    # Create a new assistant if needed
    openai_service = OpenAIService()
    assistant_id = openai_service.create_assistant_id(
        registry.get_function_definitions()
    )
    
    # Store the new assistant ID in Redis
    redis_service.set_assistant_id(assistant_id)
```

Manages OpenAI assistants by:
- Retrieving existing assistant IDs from Redis
- Creating new assistants when needed
- Storing assistant IDs for future use

### 3. Event Handler (CosmoEventHandler)

The core class managing conversation flow and events:

#### Key Methods:

1. **Initialization**:
```python
def __init__(self, websocket_service, openai_service, channel, loop, message_id, thread_id=None):
    # Initializes event handler with services and conversation identifiers
```

2. **Event Processing**:
```python
def on_event(self, event):
    # Handles different types of events:
    # - thread.run.requires_action
    # - thread.message.delta
    # - thread.message.completed
    # - thread.run.completed
```

3. **Tool Execution**:
```python
def handle_tool_calls(self, data):
    # Processes tool calls
    # Sends execution status via WebSocket
```

### 4. Conversation Management

#### Thread Management
```python
# Get thread ID from Redis or create a new one
thread_id = redis_service.get_thread_id(channel)

# If no thread ID exists for this channel, create a new thread
if not thread_id:
    thread = openai_service.create_thread()
    thread_id = thread.id
    # Store the new thread ID in Redis
    redis_service.set_thread_id(channel, thread_id)
    # Initialize metadata
    redis_service.set_thread_metadata(
        channel,
        {
            "created_at": time.time(),
            "message_count": 0,
            "last_message_at": time.time(),
        },
    )
```

- Creates or retrieves conversation threads
- Maps channel identifiers to thread IDs in Redis
- Maintains metadata about conversations

#### Message Creation
```python
message_obj = openai_service.create_message(
    thread_id, message, event_handler=event_handler
)
```
- Adds user messages to the conversation
- Associates messages with specific threads

### 5. Main Conversation Flow

```python
def run_conversation(message, channel, message_id, properties=None):
    # 1. Get assistant ID from Redis
    assistant_id = redis_service.get_assistant_id()
    
    # 2. Setup event loop and services
    loop = asyncio.new_event_loop()
    openai_service = OpenAIService()
    websocket_service = WebSocketService()
    
    # 3. Initialize WebSocket connection and subscribe to channel
    loop.run_until_complete(websocket_service.connect())
    loop.run_until_complete(websocket_service.subscribe(channel))
    
    # 4. Get or create thread ID from Redis
    thread_id = redis_service.get_thread_id(channel)
    
    # 5. Create event handler
    event_handler = CosmoEventHandler(
        websocket_service, openai_service, channel, loop, message_id, thread_id
    )
    
    # 6. Create message and start conversation
    openai_service.create_message(thread_id, message, event_handler=event_handler)
    openai_service.stream_conversation(
        thread_id=thread_id,
        assistant_id=assistant_id,
        event_handler=event_handler
    )
    
    # 7. Wait for completion or timeout
    # 8. Clean up resources
```

## Message Processing Flow

1. **Message Reception**:
   - Receives messages from RabbitMQ
   - Validates required fields (message, channel, message_id)
   - Passes to conversation handler

2. **Processing**:
   - Retrieves or creates thread ID for the channel
   - Creates message in OpenAI thread
   - Streams conversation with the assistant
   - Handles tool calls as needed

3. **Output**:
   - Streams response via WebSocket
   - Sends status updates (started, processing, responding, in_progress, completed)
   - Provides error handling and timeout management

## Thread Management

### Thread Persistence
- Thread IDs are stored in Redis with channel identifiers as keys
- Metadata includes creation time, message count, and last activity
- Threads expire after 90 days by default

### Thread Cleanup Commands
```python
def clear_all_threads():
    # Delete all thread IDs and metadata from Redis
    # Requires confirmation to prevent accidental data loss

def clear_old_threads(days):
    # Delete threads older than specified number of days
    # Based on last message timestamp

def show_thread_stats():
    # Display statistics about threads in Redis
    # Includes age distribution, message counts, and storage usage
```

## Error Handling

The application includes comprehensive error handling:

1. **Connection Errors**:
   - WebSocket connection failures
   - RabbitMQ connection issues
   - Redis connectivity problems

2. **Processing Errors**:
   - Invalid message format
   - Missing required fields
   - Tool execution failures

3. **Timeout Handling**:
   - No initial response within 45 seconds
   - No updates for 60 seconds after starting
   - Overall processing timeout of 90 seconds

4. **Error Reporting**:
   - WebSocket error messages with details
   - Logging for debugging
   - Dead letter queue for failed messages

## Testing and Utilities

```python
def test_message(channel_id, message):
    # Test sending a message directly without RabbitMQ
    # Uses the same processing flow as production

def generate_uuid():
    # Generate a channel identifier for testing
    # Creates a thread ID in Redis
```

## RabbitMQ Integration

```python
def main():
    # Main RabbitMQ consumer loop
    # Sets up exchanges, queues, and dead letter handling
    # Processes messages with proper acknowledgment
```

Key features:
- Durable queues and exchanges
- Message priority support
- Dead letter exchange for failed messages
- Automatic reconnection
- Multiple worker support

## Usage Example

```python
if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Handle command-line arguments for utilities
        # --generate-uuid, --test-message, etc.
    else:
        main()  # Start RabbitMQ consumer
```

This starts the application and:
1. Initializes all components
2. Sets up RabbitMQ consumer
3. Processes incoming messages
4. Manages conversation threads
5. Streams responses via WebSocket 