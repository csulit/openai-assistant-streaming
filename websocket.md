# WebSocket Implementation Documentation

## Overview

Our WebSocket implementation enables real-time communication between the AI assistant and a WebSocket server. The system sends live updates about the conversation, including processing status, tool execution, and response streaming.

## Architecture

### WebSocketService

The `WebSocketService` class handles all WebSocket-related operations:

```python
class WebSocketService:
    def __init__(self, uri: str = settings.WEBSOCKET_URL):
        self.uri = uri          # WebSocket server URL
        self.websocket = None   # WebSocket connection
        self.subscribed_channels = set()  # Channels subscribed to
        self.max_retries = 3    # Max retries for operations
        self.retry_delay = 1.0  # Delay between retries
        self.ping_interval = 30.0  # Interval for ping/pong health checks
```

### Connection Flow

1. **Initial Connection**:
   ```python
   # Configuration from settings
   WEBSOCKET_URL = "ws://localhost:8080/ws"
   
   # Initialize service
   websocket_service = WebSocketService()
   
   # Connect to WebSocket server
   loop.run_until_complete(websocket_service.connect())
   ```

2. **Subscription Process**:
   ```json
   // Subscribe Message
   {
     "channel": "subscription",
     "payload": {
       "action": "subscribe",
       "channel": "user_session_abc123"
     }
   }
   ```

## Message Types

### 1. Status Messages

```json
// Processing Started
{
  "channel": "user_session_abc123",
  "payload": {
    "message": "Assistant is processing your request...",
    "timestamp": 1683042123.456,
    "status": "started",
    "type": "status",
    "final_message": false,
    "message_id": "unique-message-id",
    "thread_id": "thread_abc123"
  }
}

// Tool Execution
{
  "channel": "user_session_abc123",
  "payload": {
    "message": "Executing weather check for Makati",
    "timestamp": 1683042124.123,
    "status": "processing",
    "type": "tool",
    "final_message": false,
    "message_id": "unique-message-id",
    "thread_id": "thread_abc123"
  }
}
```

### 2. Response Messages

```json
// Responding Status
{
  "channel": "user_session_abc123",
  "payload": {
    "message": "Assistant is responding...",
    "timestamp": 1683042125.456,
    "status": "responding",
    "type": "status",
    "final_message": false,
    "message_id": "unique-message-id",
    "thread_id": "thread_abc123"
  }
}

// Streaming Response
{
  "channel": "user_session_abc123",
  "payload": {
    "message": "Current weather in Makati...",
    "timestamp": 1683042126.789,
    "status": "in_progress",
    "type": "response",
    "final_message": false,
    "message_id": "unique-message-id",
    "thread_id": "thread_abc123"
  }
}

// Completion Message
{
  "channel": "user_session_abc123",
  "payload": {
    "message": "Complete response...",
    "timestamp": 1683042127.123,
    "status": "completed",
    "type": "response",
    "final_message": true,
    "message_id": "unique-message-id",
    "thread_id": "thread_abc123"
  }
}
```

### 3. Error Messages

```json
{
  "channel": "user_session_abc123",
  "payload": {
    "message": "Error description",
    "timestamp": 1683042128.456,
    "status": "error",
    "type": "error",
    "error_details": "Detailed error information",
    "message_id": "unique-message-id",
    "thread_id": "thread_abc123"
  }
}
```

## Integration with Event Handler

The `CosmoEventHandler` class integrates with the WebSocket service to send updates at different stages:

1. **Initial Processing**:
   ```python
   # Send initial status message
   status_message = {
       "message": "Assistant is processing your request...",
       "timestamp": time.time(),
       "status": "started",
       "type": "status",
       "final_message": False,
       "message_id": self.message_id,
       "thread_id": self.current_thread_id,
   }
   self.loop.run_until_complete(
       self.ws_service.send_message(self.channel, status_message)
   )
   ```

2. **Tool Execution**:
   ```python
   # Send tool execution status
   status_message = {
       "message": f"Executing {tool_call.function.name}...",
       "timestamp": time.time(),
       "status": "processing",
       "type": "tool",
       "final_message": False,
       "message_id": self.message_id,
       "thread_id": self.current_thread_id,
   }
   self.loop.run_until_complete(
       self.ws_service.send_message(self.channel, status_message)
   )
   ```

3. **Response Streaming**:
   ```python
   # Send responding status on first delta
   status_message = {
       "message": "Assistant is responding...",
       "timestamp": time.time(),
       "status": "responding",
       "type": "status",
       "final_message": False,
       "message_id": self.message_id,
       "thread_id": self.current_thread_id,
   }
   self.loop.run_until_complete(
       self.ws_service.send_message(self.channel, status_message)
   )
   
   # Send content chunks during streaming
   message_data = {
       "message": self.message_content,
       "timestamp": current_time,
       "status": "in_progress",
       "type": "response",
       "final_message": False,
       "message_id": self.message_id,
       "thread_id": self.current_thread_id,
   }
   self.loop.run_until_complete(
       self.ws_service.send_message(self.channel, message_data)
   )
   ```

4. **Completion**:
   ```python
   # Send final message
   final_message = {
       "message": self.message_content,
       "timestamp": time.time(),
       "status": "completed",
       "type": "response",
       "final_message": True,
       "message_id": self.message_id,
       "thread_id": self.current_thread_id,
   }
   self.loop.run_until_complete(
       self.ws_service.send_message(self.channel, final_message)
   )
   ```

## Message Flow

1. **Connection Initialization**:
   - Create event loop
   - Initialize WebSocket connection
   - Subscribe to channel

2. **During Conversation**:
   - Send "started" status when processing begins
   - Send "processing" status during tool execution
   - Send "responding" status when content generation begins
   - Send "in_progress" status during content streaming
   - Send "completed" status when finished

3. **Cleanup**:
   ```python
   # Disconnect from WebSocket
   self.loop.run_until_complete(self.ws_service.disconnect())
   ```

## Error Handling

The implementation includes comprehensive error handling:

1. **Connection Errors**:
   - Automatic reconnection attempts with configurable retries
   - Subscription failure handling
   - Ping/pong health checks to detect disconnections

2. **Message Sending Errors**:
   - Retry mechanism for failed message delivery
   - Timeout handling for send operations
   - Logging of all errors for debugging

## Best Practices

1. **Message Structure**:
   - Consistent payload format with channel and payload fields
   - Include timestamps for all messages
   - Include thread_id and message_id for tracking
   - Use clear status and type indicators

2. **Connection Management**:
   - Initialize connection before use
   - Subscribe to channels explicitly
   - Implement health checks with ping/pong
   - Clean disconnection when finished

3. **Error Recovery**:
   - Implement automatic reconnection
   - Resubscribe to channels after reconnection
   - Use timeouts for all operations
   - Log all errors for debugging

## Example Usage

```python
# Initialize WebSocket service
websocket_service = WebSocketService()

# Connect to WebSocket server
loop.run_until_complete(websocket_service.connect())
loop.run_until_complete(websocket_service.subscribe(channel))

# Create event handler with WebSocket support
event_handler = CosmoEventHandler(
    websocket_service, 
    openai_service, 
    channel, 
    loop, 
    message_id
)

# Messages will be automatically sent during conversation

# Disconnect when finished
loop.run_until_complete(websocket_service.disconnect())
```

## Server-Side Expectations

The WebSocket server should handle:
1. Subscription/unsubscription requests via the "subscription" channel
2. Message broadcasting to subscribers
3. Channel-based message routing
4. Connection management and health checks
5. Error responses

The server processes messages based on the channel field and broadcasts to appropriate subscribers. 