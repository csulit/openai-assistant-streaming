# Kuya Kim Weather Assistant

A real-time weather assistant powered by OpenAI's Assistant API, featuring WebSocket integration for live updates. The assistant provides weather information and KMC business analytics through a conversational interface.

## Overview

This application combines OpenAI's Assistant API with real-time weather data and KMC's business data to create an engaging assistant with dual personalities: a friendly weather expert (Kuya Kim) and a professional business analyst. It provides weather information with a dash of humor and business analytics with precision, all streamed in real-time through WebSocket connections.

## Features

- 🤖 OpenAI Assistant Integration
- 🌤️ Real-time Weather Data
- 📊 KMC Business Analytics
- 📡 WebSocket Live Updates
- 🎯 Focused Domain Queries
- 😊 Contextual Personality Switching

## Documentation

The project is documented in several files:

1. [Main Application Documentation](main.py.md)
   - Core application structure
   - Event handling system
   - Conversation management
   - Tool integration
   - Error handling

2. [WebSocket Implementation](websocket.md)
   - Real-time communication
   - Message types and formats
   - Connection management
   - Event streaming
   - Error notifications

3. [Contributing Guide](contributing.md)
   - How to extend the assistant
   - Adding new tools
   - Best practices
   - Development guidelines

## Quick Start

1. Set up environment variables in `.env`:
   ```bash
   # OpenAI Configuration
   OPENAI_API_KEY=your_openai_key
   OPENAI_MODEL=gpt-4-1106-preview
   OPENAI_ASSISTANT_ID=your_assistant_id

   # Weather API Configuration
   OPENWEATHER_API_KEY=your_weather_key

   # WebSocket Configuration
   WEBSOCKET_URI=wss://your-websocket-server/
   WEBSOCKET_CHANNEL=weather-update

   # Database Configuration
   MSSQL_CONNECTION_STRING="Driver={ODBC Driver 18 for SQL Server};Server=your_server;Database=your_db;UID=your_username;PWD=your_password;TrustServerCertificate=yes;"

   # Environment
   NODE_ENV=development
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start the WebSocket server (the server specified in WEBSOCKET_URI)

4. Run the assistant:
   ```bash
   python main.py
   ```

## Message Types

The assistant sends different types of messages through WebSocket:

```json
{
    "type": "weather-update",
    "payload": {
        "message": "Content (weather info or business data)",
        "timestamp": 1234567890,
        "status": "in_progress|completed|error",
        "type": "response|error"
    }
}
```

## Architecture

```
├── app/
│   ├── core/              # Core configuration
│   └── tools/             # Assistant tools
│       ├── weather.py     # Weather information tool
│       ├── kmc_active_clients.py  # KMC client analytics tool
│       ├── registry.py    # Tool registration system
│       └── base.py        # Base tool classes
├── main.py               # Main application
├── contributing.md       # Contributing guide
├── main.py.md           # Main app documentation
├── websocket.md         # WebSocket documentation
└── README.md            # This file
```

## Development

For development guidelines and how to extend the assistant's capabilities, please refer to:
- [Contributing Guide](contributing.md) for adding new tools
- [Main Application Documentation](main.py.md) for core functionality
- [WebSocket Implementation](websocket.md) for real-time features

## Error Handling

The application includes comprehensive error handling:
- Connection errors (WebSocket, Database, API)
- Query execution errors
- Tool execution errors
- Message processing errors

All errors are logged and streamed through WebSocket with appropriate status codes.

## Best Practices

1. **Tool Development**
   - Follow the guidelines in [contributing.md](contributing.md)
   - Maintain consistent error handling
   - Include proper documentation
   - Use specific, focused tool names

2. **WebSocket Communication**
   - Follow the message format in [websocket.md](websocket.md)
   - Handle connection states properly
   - Implement proper cleanup

3. **Event Handling**
   - Follow patterns in [main.py.md](main.py.md)
   - Maintain proper error propagation
   - Ensure proper resource cleanup

## License

MIT License - Feel free to use and modify as needed.

## Contributing

Please read [contributing.md](contributing.md) for details on adding new features or tools to the assistant. 