# OpenAI Assistant Streaming Service

A scalable service for streaming OpenAI Assistant responses via WebSockets, with RabbitMQ for message queuing and Redis for conversation persistence.

## Architecture Overview

This service implements a scalable architecture for handling OpenAI Assistant conversations:

1. **RabbitMQ Queue**: Receives incoming message requests
2. **Redis**: Stores mappings between channel identifiers and OpenAI thread IDs
3. **WebSocket Server**: Streams responses back to clients
4. **OpenAI API**: Processes messages and generates responses

### Message Flow

```
Client → RabbitMQ → Worker → OpenAI API → WebSocket → Client
```

1. Client sends a message to RabbitMQ with a channel identifier (UUID, Convex ID, or custom string) and message ID
2. Worker processes the message, looking up or creating an OpenAI thread ID
3. Worker streams the response back to the client via WebSocket
4. Conversation history is maintained in OpenAI threads, mapped to channel identifiers in Redis

### Channel Identifiers

The system supports various types of channel identifiers:

- **UUIDs**: Traditional unique identifiers (default for CLI testing)
- **Convex IDs**: Direct integration with Convex document IDs
- **Custom Strings**: Any unique string that can identify a conversation

## Configuration

Configuration is managed through environment variables:

### OpenAI Settings
- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_MODEL`: Model to use (default: "gpt-4o-mini")

### RabbitMQ Settings
- `RABBITMQ_URL`: RabbitMQ connection URL (default: "amqp://guest:guest@localhost:5672/")
- `QUEUE_NAME`: Queue name (default: "cosmo_queue")
- `ROUTING_KEY`: Routing key (default: "cosmo_key")
- `EXCHANGE_NAME`: Exchange name (default: "cosmo_exchange")

### WebSocket Settings
- `WEBSOCKET_URL`: WebSocket server URL (default: "ws://localhost:8080/ws")

### Redis Settings
- `REDIS_URL`: Redis connection URL (default: "redis://localhost:6379/0")
- `REDIS_PREFIX`: Key prefix for Redis (default: "cosmo:")
- `REDIS_THREAD_EXPIRY`: Thread expiry time in seconds (default: 7776000 - 90 days)

### Tool Settings
- `OPENWEATHER_API_KEY`: OpenWeather API key for weather tool

## Message Format

### Input Message (RabbitMQ)

The following JSON format is required when sending messages to RabbitMQ:

```json
{
  "channel": "unique-channel-identifier",
  "message_id": "unique-message-id",
  "message": "User's message text"
}
```

#### Field Descriptions:

- `channel`: Unique identifier for the conversation channel
  - Can be a UUID, Convex ID, or any unique string
  - Used to map to an OpenAI thread ID in Redis
  - Persists conversation context across multiple messages
  - For Convex integration, you can use Convex document IDs directly

- `message_id`: Unique identifier for this specific message
  - Used to correlate requests with responses
  - Included in all WebSocket messages related to this request
  - Can be any string, but should be unique per message

- `message`: The user's message text
  - The actual content to send to the OpenAI assistant
  - Plain text format

#### Examples:

With UUID as channel (default for CLI testing):
```json
{
  "channel": "550e8400-e29b-41d4-a716-446655440000",
  "message_id": "msg-123456789",
  "message": "What is the capital of France?"
}
```

With Convex ID as channel:
```json
{
  "channel": "convex_id_12345",
  "message_id": "msg-123456789",
  "message": "What is the capital of France?"
}
```

With custom string as channel:
```json
{
  "channel": "user_session_abc123",
  "message_id": "msg-123456789",
  "message": "What is the capital of France?"
}
```

### Output Messages (WebSocket)

Status messages:
```json
{
  "message": "Assistant is processing your request...",
  "timestamp": 1683042123.456,
  "status": "started",
  "type": "status",
  "final_message": false,
  "message_id": "unique-message-id",
  "thread_id": "thread_abc123"
}
```

Response messages:
```json
{
  "message": "Response content...",
  "timestamp": 1683042124.789,
  "status": "in_progress",
  "type": "response",
  "final_message": false,
  "message_id": "unique-message-id",
  "thread_id": "thread_abc123"
}
```

Final message:
```json
{
  "message": "Complete response content...",
  "timestamp": 1683042125.123,
  "status": "completed",
  "type": "response",
  "final_message": true,
  "message_id": "unique-message-id",
  "thread_id": "thread_abc123"
}
```

Error message:
```json
{
  "message": "Error description",
  "timestamp": 1683042126.456,
  "status": "error",
  "type": "error",
  "error_details": "Detailed error information",
  "message_id": "unique-message-id",
  "thread_id": "thread_abc123"
}
```

## Status Types

- `started`: Initial processing has begun
- `processing`: Assistant is gathering information (tool execution)
- `responding`: Assistant has started generating a response
- `in_progress`: Content is being streamed
- `completed`: Response is complete
- `error`: An error occurred

## Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up environment variables (see Configuration section)
4. Start the service:
   ```
   python main.py
   ```

## Testing

You can test the service using the built-in test command:

```
python main.py --test-message <channel_identifier> "Your test message"
```

This will:
1. Generate a test message ID
2. Look up or create an OpenAI thread ID for the channel identifier in Redis
3. Send the message to the OpenAI Assistant
4. Stream the response via WebSocket
5. Automatically exit when the conversation is complete

### Channel Identifiers

The channel identifier can be any string value:

- **UUID**: Generate a random UUID with `python main.py --generate-uuid`
- **Convex ID**: Use a Convex document ID directly (e.g., `convex_id_12345`)
- **Custom String**: Use any unique string identifier (e.g., `user_session_abc123`)

The system will:
- Use an existing thread if one is mapped to this channel identifier in Redis
- Create a new thread if no mapping exists
- Update thread metadata with message counts and timestamps

### Example Test Commands

Test with a generated UUID:
```
# First generate a UUID
python main.py --generate-uuid
# Then use the generated UUID
python main.py --test-message 550e8400-e29b-41d4-a716-446655440000 "Hello, assistant!"
```

Test with a Convex ID:
```
python main.py --test-message convex_id_12345 "Hello, assistant!"
```

Test with a custom identifier:
```
python main.py --test-message user_session_abc123 "Hello, assistant!"
```

### Thread Management Commands

The service provides commands to manage conversation threads in Redis:

```
# Generate a new UUID and thread
python main.py --generate-uuid

# Show statistics about threads in Redis
python main.py --show-thread-stats

# Clear all threads from Redis (keeps assistant ID)
python main.py --clear-all-threads

# Clear threads older than a specific number of days
python main.py --clear-old-threads 30
```

The thread statistics command provides insights into:
- Total number of threads and their age distribution
- Message counts and activity levels
- Oldest and newest conversations
- Storage usage in Redis

The cleanup commands help maintain system performance by:
- Removing abandoned conversations
- Freeing up Redis storage space
- Allowing for periodic maintenance

Both cleanup commands include confirmation prompts to prevent accidental data loss.

## Recent Changes

### Convex Integration

The service now explicitly supports using Convex document IDs as channel identifiers, making integration with Convex applications seamless:

1. **Direct ID Usage**: Use Convex document IDs directly as channel identifiers in RabbitMQ messages
2. **Conversation Persistence**: Conversations are automatically associated with Convex documents
3. **No UUID Conversion**: No need to generate or store UUIDs separately - use your existing Convex IDs

#### Integration Example

In your Convex backend:
```typescript
// Get a Convex document ID
const conversationId = conversation._id.toString();

// Send a message to RabbitMQ using the Convex ID as the channel
await sendToRabbitMQ({
  channel: conversationId,  // Use Convex ID directly
  message_id: generateMessageId(),
  message: userMessage
});
```

In your frontend:
```javascript
// Subscribe to WebSocket using the same Convex ID
const socket = new WebSocket('ws://your-websocket-server/ws');
socket.onopen = () => {
  socket.send(JSON.stringify({
    action: 'subscribe',
    channel: conversationId  // Same Convex ID used in RabbitMQ
  }));
};

// Handle incoming messages
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Process response from assistant
};
```

### Assistant ID Management in Redis

The service stores the OpenAI Assistant ID in Redis:

1. **Automatic Assistant Creation**: If no assistant ID is found in Redis, the service automatically creates a new assistant and stores its ID in Redis
2. **Persistence Across Restarts**: The assistant ID is stored permanently in Redis, allowing the service to use the same assistant across restarts
3. **Verification**: The service verifies that the assistant exists in OpenAI before using it
4. **Fallback**: If the assistant ID in Redis is invalid, the service creates a new assistant

### Redis Integration

The service now uses Redis to maintain mappings between channel UUIDs and OpenAI thread IDs. This enables:

1. **Conversation Persistence**: Conversations continue across multiple messages
2. **Scalability**: Multiple worker instances can handle messages for the same conversation
3. **Metadata Storage**: Track message counts, timestamps, and other metadata
4. **Time-Limited Storage**: Channel-to-thread mappings automatically expire after 90 days of inactivity

### Conversation Expiry

To manage storage and maintain system performance, conversation data follows these expiry rules:

1. **90-Day Retention**: Channel-to-thread mappings and metadata expire after 90 days of inactivity
2. **Activity-Based Refresh**: Each time a conversation is accessed, its expiry timer resets
3. **Automatic Cleanup**: Expired conversations are automatically removed from Redis
4. **New Thread Creation**: If a message is sent to an expired channel, a new thread is created

This approach ensures:
- Long-term persistence for active conversations
- Automatic cleanup of abandoned conversations
- Efficient resource utilization
- Compliance with data retention best practices

### Message ID Tracking

All messages now include a `message_id` field that is:
1. Required in the RabbitMQ input message
2. Included in all WebSocket response messages
3. Used for client-side correlation of requests and responses

### WebSocket Status Updates

The service now sends detailed status updates via WebSocket:
1. Initial "started" status when processing begins
2. "processing" status during tool execution
3. "responding" status when content generation begins
4. "in_progress" status during content streaming
5. "completed" status when finished

## License

[MIT License](LICENSE) 