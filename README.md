# OpenAI Assistant Streaming Service

This service handles streaming conversations with OpenAI's Assistant API, managing WebSocket connections for real-time updates, and processing tool calls.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables in `.env`:
```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_ASSISTANT_ID=your_assistant_id  # Set after creating assistant
WEBSOCKET_URI=your_websocket_uri
RABBITMQ_URL=your_rabbitmq_url
QUEUE_NAME=your_queue_name
ROUTING_KEY=your_routing_key
EXCHANGE_NAME=your_exchange_name
OPENWEATHER_API_KEY=your_weather_api_key
```

## Usage

### Starting the Service
```bash
python main.py
```

### Managing the Assistant

#### Creating an Assistant
Before running the service for the first time, create an assistant:
```bash
python main.py --create-assistant
```
This will output an assistant ID that you should save in your `.env` file as `OPENAI_ASSISTANT_ID=<id>`.

#### Deleting an Assistant
To delete an existing assistant:
```bash
python main.py --delete-assistant <assistant_id>
```

### Generating Test Thread IDs
To generate a thread ID for testing purposes:
```bash
python main.py --generate-thread
```
This will output a thread ID in the following format:
```
=== TEST THREAD ID ===
thread_xyz123...
=====================
```
You can use this thread ID for testing the service with your WebSocket client.

## Architecture

- Uses RabbitMQ for message queuing
- WebSocket for real-time communication
- OpenAI Assistant API for conversation handling
- Supports multiple tools:
  - Weather information
  - KMC active clients data
  - KMC available offices information

## Error Handling

The service includes comprehensive error handling for:
- Thread not found cases
- WebSocket connection issues
- Timeouts
- API errors

Each error is properly logged and communicated back through the WebSocket connection.

## Development

When testing locally:
1. Generate a test thread ID using the command above
2. Use the thread ID as the channel in your WebSocket messages
3. The service will validate the thread existence before processing messages

For more detailed documentation, see the individual module docstrings. 