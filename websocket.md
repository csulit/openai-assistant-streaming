# WebSocket Implementation Documentation

## Overview

Our WebSocket implementation enables real-time communication between the AI assistant and a WebSocket server. The system sends live updates about the conversation, weather data retrieval, and tool execution status.

## Architecture

### WebSocket Manager

The `WebSocketManager` class handles all WebSocket-related operations:

```python
class WebSocketManager:
    def __init__(self, uri, channel):
        self.uri = uri          # WebSocket server URL
        self.channel = channel  # Channel to subscribe to
        self.websocket = None   # WebSocket connection
        self.is_subscribed = False
        self.loop = None        # Async event loop
```

### Connection Flow

1. **Initial Connection**:
   ```python
   # Configuration
   WEBSOCKET_URI = "ws://localhost:4000"
   WEBSOCKET_CHANNEL = "weather-update"
   ```

2. **Subscription Process**:
   ```json
   // Subscribe Message
   {
     "type": "subscribe",
     "payload": {
       "channel": "weather-update"
     }
   }

   // Server Response
   {
     "type": "subscribed",
     "payload": {
       "channel": "weather-update",
       "message": "subscribed"
     }
   }
   ```

## Message Types

### 1. Tool Execution Messages

```json
// Tool Start
{
  "type": "weather-update",
  "payload": {
    "message": "Executing weather check for Makati",
    "timestamp": 1234567890,
    "thread_id": "thread_xyz",
    "status": "started",
    "type": "tool"
  }
}

// Tool Result
{
  "type": "weather-update",
  "payload": {
    "message": "{\"temperature\": 30.14, ...}",
    "timestamp": 1234567890,
    "thread_id": "thread_xyz",
    "status": "tool_executed",
    "type": "tool"
  }
}
```

### 2. AI Response Messages

```json
// Streaming Response
{
  "type": "weather-update",
  "payload": {
    "message": "Current weather in Makati...",
    "timestamp": 1234567890,
    "thread_id": "thread_xyz",
    "type": "response"
  }
}

// Completion Message
{
  "type": "weather-update",
  "payload": {
    "message": "Complete response...",
    "timestamp": 1234567890,
    "thread_id": "thread_xyz",
    "status": "completed",
    "type": "response"
  }
}
```

## Integration with Event Handler

The `MyEventHandler` class integrates with the WebSocket manager to send updates at different stages:

1. **Delta Updates** (Streaming AI Response):
   ```python
   elif event.event == 'thread.message.delta':
       # Sends real-time updates as the AI generates response
   ```

2. **Tool Execution**:
   ```python
   def handle_tool_calls(self, data):
       # Sends updates about tool execution status
   ```

3. **Message Completion**:
   ```python
   elif event.event == 'thread.message.completed':
       # Sends final message with complete content
   ```

## Message Flow

1. **Connection Initialization**:
   - Create event loop
   - Initialize WebSocket connection
   - Subscribe to channel

2. **During Conversation**:
   - Tool execution updates
   - Real-time AI response streaming
   - Completion notifications

3. **Cleanup**:
   ```json
   // Unsubscribe Message
   {
     "type": "unsubscribe",
     "payload": {
       "channel": "weather-update"
     }
   }
   ```

## Error Handling

The implementation includes comprehensive error handling:

1. **Connection Errors**:
   - Failed connection attempts
   - Subscription failures
   - Network interruptions

2. **Message Sending Errors**:
   - Failed message delivery
   - Invalid message format
   - Connection loss during transmission

## Best Practices

1. **Message Structure**:
   - Consistent payload format
   - Include timestamps
   - Include thread IDs for tracking
   - Clear message types and status indicators

2. **Connection Management**:
   - Proper initialization
   - Clean disconnection
   - Error recovery

3. **Event Loop Handling**:
   - Single event loop per session
   - Proper loop sharing between components
   - Async operation management

## Example Usage

```python
# Initialize WebSocket manager
ws_manager = WebSocketManager(WEBSOCKET_URI, WEBSOCKET_CHANNEL)

# Create event handler with WebSocket support
event_handler = MyEventHandler(ws_manager, loop)

# Connect to WebSocket server
loop.run_until_complete(ws_manager.connect())

# Messages will be automatically sent during conversation
```

## Server-Side Expectations

The WebSocket server should handle:
1. Subscription/unsubscription requests
2. Message broadcasting to subscribers
3. Channel-based message routing
4. Connection management
5. Error responses

The server processes messages based on the `type` field and broadcasts to appropriate subscribers based on the channel. 