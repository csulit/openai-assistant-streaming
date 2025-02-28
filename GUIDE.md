# Frontend Integration Guide

This guide explains how to integrate your frontend application with our AI Assistant backend service. The system uses WebSockets for real-time communication, allowing for streaming responses and status updates.

## Architecture Overview

Our system follows this high-level architecture:

1. **Frontend Application**: Your React, Vue, Angular, or other frontend framework
2. **WebSocket Connection**: Real-time communication channel
3. **Backend Service**: Processes messages using OpenAI's Assistant API
4. **RabbitMQ**: Message queue for handling requests
5. **Redis**: Stores conversation history and thread mappings

The flow of a conversation is:

```
Frontend → RabbitMQ → Worker → WebSocket → Frontend
```

## System Flow Diagram

Below is a description for creating a visual representation of the system flow:

```
┌─────────────────┐                                              ┌─────────────────┐
│                 │                                              │                 │
│    Frontend     │                                              │    Frontend     │
│   Application   │                                              │   Application   │
│                 │                                              │                 │
└────────┬────────┘                                              └────────▲────────┘
         │                                                                │
         │                                                                │
         │ 1. User sends message                                          │ 6. Receive response
         │                                                                │    via WebSocket
         ▼                                                                │
┌─────────────────┐          ┌─────────────────┐          ┌───────────────┴─┐
│                 │          │                 │          │                 │
│    RabbitMQ     │          │     Worker      │          │    WebSocket    │
│    Message      ├─────────►│    Process      ├─────────►│     Server      │
│     Queue       │          │                 │          │                 │
│                 │          │                 │          │                 │
└─────────────────┘          └────────┬────────┘          └─────────────────┘
                                      │
                                      │ 2. Process message
                                      │
                                      ▼
                             ┌─────────────────┐
                             │                 │
                             │    OpenAI       │
                             │    Assistant    │
                             │      API        │
                             │                 │
                             └────────┬────────┘
                                      │
                                      │ 3. Get response
                                      │
                                      ▼
                             ┌─────────────────┐
                             │                 │
                             │     Redis       │
                             │   (Storage)     │
                             │                 │
                             └─────────────────┘
```

The diagram illustrates the following flow:

1. **User Interaction**: The user sends a message from the frontend application.

2. **Message Queuing**: The message is sent to RabbitMQ, which queues it for processing.

3. **Worker Processing**: A worker picks up the message from RabbitMQ and processes it.

4. **OpenAI Interaction**: The worker sends the message to OpenAI's Assistant API and receives a response.

5. **Data Storage**: Conversation history and thread mappings are stored in Redis.

6. **Response Delivery**: The worker sends the response back to the frontend via WebSocket.

7. **Frontend Update**: The frontend application receives the response and updates the UI accordingly.

## Integration Steps

### 1. Establish WebSocket Connection

First, connect to our WebSocket server and subscribe to a channel:

```javascript
// Example using a custom WebSocket hook
const { sendMessage, connectionStatus } = useWebSocket({
  url: "ws://your-backend-url/ws",
  channel: "user_session_123", // Use a unique identifier for each user/conversation
  onMessage: (data) => {
    // Handle incoming messages (covered in next section)
  }
});
```

### 2. Handle WebSocket Messages

The backend sends different types of messages through the WebSocket connection:

#### Message Types

1. **Status Updates** (`type: "status"`):
   - `started`: Initial processing has begun
   - `processing`: Assistant is executing tools
   - `responding`: Assistant has started generating a response

2. **Response Messages** (`type: "response"`):
   - `in_progress`: Content is being streamed
   - `completed`: Response is complete

3. **Error Messages** (`type: "error"`):
   - Contains error details and message

#### Example Message Handler

```javascript
const onMessage = useCallback((payload) => {
  if (typeof payload === "object" && payload !== null) {
    const data = payload;

    // Store thread and message IDs when available
    if (data.thread_id) {
      // Save thread_id for future reference
    }

    // Handle status updates
    if (data.type === "status") {
      switch (data.status) {
        case "started":
          // Show initial loading state
          break;
        case "processing":
          // Show tool execution state
          break;
        case "responding":
          // Show that the assistant is typing
          break;
      }
    }
    // Handle response messages
    else if (data.type === "response" && data.message) {
      if (data.status === "in_progress") {
        // Update UI with streaming content
      } else if (data.status === "completed") {
        // Add final message to conversation
      }
    }
    // Handle error messages
    else if (data.type === "error") {
      // Display error to user
      console.error("WebSocket error:", data.error_details);
    }
  }
}, []);
```

### 3. Send Messages to the Assistant

To send a message to the assistant:

```javascript
// Generate a unique message ID for tracking
const messageId = generateUniqueId();

// Send message through WebSocket
sendMessage({
  message: "What's the weather like in Manila?",
  message_id: messageId,
  // The channel is already specified in the WebSocket connection
});

// Add user message to local state
addMessage({
  role: "user",
  content: "What's the weather like in Manila?",
  timestamp: Date.now(),
  messageId: messageId
});
```

## Complete Integration Example

Here's a complete example using React and a custom WebSocket hook:

```jsx
import React, { useState, useCallback, useEffect } from 'react';
import useWebSocket from './hooks/useWebSocket';

function ChatInterface() {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [streamingContent, setStreamingContent] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [assistantStatus, setAssistantStatus] = useState(null);
  const [threadId, setThreadId] = useState(null);

  // Generate a unique channel ID for this conversation
  // In a real app, you might get this from user session or generate once and store
  const channelId = "user_session_" + Math.random().toString(36).substring(2, 10);

  const { sendMessage, connectionStatus } = useWebSocket({
    url: "ws://your-backend-url/ws",
    channel: channelId,
    onMessage: useCallback((payload) => {
      if (typeof payload === "object" && payload !== null) {
        const data = payload;

        // Store thread ID when available
        if (data.thread_id) {
          setThreadId(data.thread_id);
        }

        // Handle status updates
        if (data.type === "status") {
          setAssistantStatus(data.status);
          
          if (data.status === "started" || 
              data.status === "processing" || 
              data.status === "responding") {
            setIsLoading(true);
          } else if (data.status === "completed") {
            setIsLoading(false);
            setAssistantStatus(null);
          }
        }
        // Handle response messages
        else if (data.type === "response" && data.message) {
          if (data.status === "in_progress") {
            setIsLoading(false);
            setStreamingContent(data.message);
          } else if (data.status === "completed") {
            setStreamingContent(null);
            setMessages(prev => [
              ...prev,
              {
                role: "assistant",
                content: data.message,
                timestamp: data.timestamp ? data.timestamp * 1000 : Date.now(),
                messageId: data.message_id,
                threadId: data.thread_id
              }
            ]);
            setAssistantStatus(null);
          }
        }
        // Handle error messages
        else if (data.type === "error") {
          setIsLoading(false);
          setAssistantStatus(null);
          setMessages(prev => [
            ...prev,
            {
              role: "assistant",
              content: `Error: ${data.message || "An error occurred"}`,
              timestamp: Date.now(),
              isError: true
            }
          ]);
          console.error("WebSocket error:", data.error_details);
        }
      }
    }, []),
  });

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;
    
    // Generate a unique message ID
    const messageId = Date.now().toString();
    
    // Add user message to state
    setMessages(prev => [
      ...prev,
      {
        role: "user",
        content: inputValue,
        timestamp: Date.now(),
        messageId
      }
    ]);
    
    // Send message through WebSocket
    sendMessage({
      message: inputValue,
      message_id: messageId
    });
    
    // Clear input
    setInputValue('');
  };

  return (
    <div className="chat-container">
      <div className="connection-status">
        Status: {connectionStatus}
      </div>
      
      <div className="messages-container">
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.role}`}>
            <div className="message-content">{msg.content}</div>
            <div className="message-timestamp">
              {new Date(msg.timestamp).toLocaleTimeString()}
            </div>
          </div>
        ))}
        
        {streamingContent && (
          <div className="message assistant streaming">
            <div className="message-content">{streamingContent}</div>
          </div>
        )}
        
        {isLoading && (
          <div className="message-status">
            {assistantStatus === "processing" ? "Processing..." : 
             assistantStatus === "responding" ? "Typing..." : "Loading..."}
          </div>
        )}
      </div>
      
      <div className="input-container">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
          placeholder="Type a message..."
        />
        <button onClick={handleSendMessage}>Send</button>
      </div>
    </div>
  );
}

export default ChatInterface;
```

## WebSocket Hook Implementation

Here's an example implementation of the WebSocket hook used in the example above:

```javascript
import { useState, useEffect, useRef, useCallback } from 'react';

const useWebSocket = ({ url, channel, onMessage }) => {
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const socketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) return;
    
    try {
      setConnectionStatus('connecting');
      const socket = new WebSocket(url);
      
      socket.onopen = () => {
        setConnectionStatus('connected');
        // Subscribe to channel
        socket.send(JSON.stringify({
          channel: 'subscription',
          payload: {
            action: 'subscribe',
            channel: channel
          }
        }));
      };
      
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Only process messages for our channel
          if (data.channel === channel) {
            onMessage(data.payload);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };
      
      socket.onclose = () => {
        setConnectionStatus('disconnected');
        // Attempt to reconnect after delay
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, 3000);
      };
      
      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        socket.close();
      };
      
      socketRef.current = socket;
    } catch (error) {
      console.error('Failed to connect to WebSocket:', error);
      setConnectionStatus('error');
    }
  }, [url, channel, onMessage]);

  // Send message through WebSocket
  const sendMessage = useCallback((data) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected');
      return false;
    }
    
    try {
      socketRef.current.send(JSON.stringify({
        channel: channel,
        message: data.message,
        message_id: data.message_id
      }));
      return true;
    } catch (error) {
      console.error('Error sending message:', error);
      return false;
    }
  }, [channel]);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    
    return () => {
      // Clean up
      if (socketRef.current) {
        // Unsubscribe from channel
        if (socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(JSON.stringify({
            channel: 'subscription',
            payload: {
              action: 'unsubscribe',
              channel: channel
            }
          }));
        }
        socketRef.current.close();
      }
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect, channel]);

  return {
    connectionStatus,
    sendMessage,
    reconnect: connect
  };
};

export default useWebSocket;
```

## Message Format Reference

### Input Messages (Frontend to Backend)

```json
{
  "channel": "user_session_123",
  "message": "What's the weather like in Manila?",
  "message_id": "msg_1234567890"
}
```

### Output Messages (Backend to Frontend)

#### Status Messages

```json
{
  "channel": "user_session_123",
  "payload": {
    "message": "Assistant is processing your request...",
    "timestamp": 1683042123.456,
    "status": "started",
    "type": "status",
    "final_message": false,
    "message_id": "msg_1234567890",
    "thread_id": "thread_abc123"
  }
}
```

#### Response Messages

```json
{
  "channel": "user_session_123",
  "payload": {
    "message": "The current weather in Manila is...",
    "timestamp": 1683042124.789,
    "status": "in_progress",
    "type": "response",
    "final_message": false,
    "message_id": "msg_1234567890",
    "thread_id": "thread_abc123"
  }
}
```

#### Error Messages

```json
{
  "channel": "user_session_123",
  "payload": {
    "message": "Unable to process your request",
    "timestamp": 1683042125.123,
    "status": "error",
    "type": "error",
    "error_details": "Detailed error information",
    "message_id": "msg_1234567890",
    "thread_id": "thread_abc123"
  }
}
```

## Best Practices

1. **Channel Management**:
   - Use unique identifiers for channels (user IDs, session IDs, etc.)
   - Store channel IDs for returning users to maintain conversation history

2. **Error Handling**:
   - Implement reconnection logic for WebSocket disconnections
   - Display user-friendly error messages
   - Log detailed error information for debugging

3. **UI Considerations**:
   - Show appropriate loading states based on status messages
   - Implement typing indicators during "responding" status
   - Handle streaming content updates smoothly to avoid UI jank

4. **Performance**:
   - Use request animation frames for UI updates during streaming
   - Implement debouncing for rapid message updates
   - Consider virtualized lists for long conversation histories

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failures**:
   - Check that the WebSocket URL is correct
   - Ensure the backend service is running
   - Verify network connectivity and firewall settings

2. **Message Not Being Processed**:
   - Confirm the message format is correct
   - Check that the channel ID is properly set
   - Verify that a unique message_id is included

3. **No Response Received**:
   - Check WebSocket connection status
   - Verify that you're subscribed to the correct channel
   - Ensure the backend service is functioning properly

### Debugging Tips

1. Enable WebSocket logging:
   ```javascript
   // Add this to your WebSocket initialization
   socket.onmessage = (event) => {
     console.log('WebSocket message received:', event.data);
     // Regular message handling
   };
   ```

2. Monitor network traffic in browser developer tools

3. Implement a ping/pong mechanism to verify connection health

## Support

If you encounter issues not covered in this guide, please contact our support team at support@example.com or open an issue in our GitHub repository. 