# Main Application Documentation

## Overview

The `main.py` file serves as the core of our AI weather assistant application. It integrates OpenAI's Assistant API with a weather service and WebSocket communication to provide real-time weather information with a conversational interface.

## Core Components

### 1. Configuration and Initialization

```python
# OpenAI Configuration
client = OpenAI(api_key=settings.OPENAI_API_KEY)
ASSISTANT_ID = settings.OPENAI_ASSISTANT_ID
OPENAI_MODEL = settings.OPENAI_MODEL

# Tool Registration
weather_tool = WeatherTool(settings.OPENWEATHER_API_KEY)
registry.register(weather_tool)
```

The application initializes with:
- OpenAI client configuration
- Weather tool registration
- WebSocket manager setup

### 2. Assistant Creation

```python
assistant = client.beta.assistants.create(
    model=OPENAI_MODEL,
    name="My Assistant",
    tools=[{"type": "function", "function": func} for func in function_definitions],
    instructions="""I am Kuya Kim, your friendly weather expert!..."""
)
```

Creates an OpenAI assistant with:
- Specific personality (Kuya Kim)
- Weather-focused functionality
- Access to weather tools

### 3. Event Handler (MyEventHandler)

The core class managing conversation flow and events:

#### Key Methods:

1. **Initialization**:
```python
def __init__(self, websocket_manager, loop=None):
    # Initializes event handler with WebSocket support
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
    # Processes tool calls (weather queries)
    # Sends execution status via WebSocket
```

### 4. Conversation Management

#### Thread Creation
```python
def create_thread():
    return client.beta.threads.create()
```
- Creates a new conversation thread
- Returns thread ID for tracking

#### Message Creation
```python
def create_message(thread_id, message):
    return client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )
```
- Adds user messages to the conversation
- Associates messages with specific threads

### 5. Main Conversation Flow

```python
def run_conversation():
    # 1. Setup
    loop = asyncio.new_event_loop()
    event_handler = MyEventHandler(ws_manager, loop)
    
    # 2. Initialize WebSocket
    loop.run_until_complete(ws_manager.connect())
    
    # 3. Create conversation thread
    thread = create_thread()
    
    # 4. Start conversation
    with client.beta.threads.runs.stream(...) as stream:
        stream.until_done()
```

## Event Flow

1. **User Input**:
   - Creates new thread
   - Adds user message
   - Starts conversation stream

2. **Processing**:
   - Assistant receives message
   - Determines if weather tool needed
   - Executes weather queries
   - Generates response

3. **Output**:
   - Streams response via WebSocket
   - Sends tool execution updates
   - Provides completion status

## Tool Integration

### Weather Tool Execution Flow:

1. **Trigger**:
   ```python
   # When weather information is requested
   result = self.loop.run_until_complete(
       registry.execute_function(tool.function.name, arguments)
   )
   ```

2. **Processing**:
   - Calls OpenWeather API
   - Formats weather data
   - Returns structured response

3. **Response**:
   - Sends weather data via WebSocket
   - Incorporates into assistant's response

## Error Handling

The application includes comprehensive error handling:

1. **Connection Errors**:
   - WebSocket connection failures
   - API call failures
   - Network issues

2. **Processing Errors**:
   - Invalid tool calls
   - Failed weather queries
   - Message processing errors

3. **Cleanup**:
   - Proper resource cleanup
   - Connection termination
   - Error logging

## Best Practices

1. **Async Operations**:
   - Proper event loop management
   - Async/await pattern usage
   - Resource cleanup

2. **State Management**:
   - Thread tracking
   - Message history
   - Connection state

3. **Error Recovery**:
   - Graceful error handling
   - User feedback
   - Logging for debugging

## Usage Example

```python
if __name__ == "__main__":
    run_conversation()
```

This starts the application and:
1. Initializes all components
2. Connects to WebSocket server
3. Creates conversation thread
4. Processes user input
5. Streams responses
6. Handles cleanup

## Dependencies

- `openai`: OpenAI API client
- `websockets`: WebSocket communication
- `asyncio`: Asynchronous I/O
- Custom tools (`app.tools`) 