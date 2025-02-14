# Kuya Kim Weather Assistant

A real-time weather assistant powered by OpenAI's Assistant API, featuring WebSocket integration for live updates and a weather-focused conversational interface.

## Overview

This application combines OpenAI's Assistant API with real-time weather data to create an engaging weather assistant with the personality of Kuya Kim. It provides weather information with a dash of humor and streams responses in real-time through WebSocket connections.

## Features

- 🤖 OpenAI Assistant Integration
- 🌤️ Real-time Weather Data
- 📡 WebSocket Live Updates
- 🎯 Focused Weather Queries
- 😊 Engaging Personality (Kuya Kim)

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

1. Set up environment variables:
   ```bash
   OPENAI_API_KEY=your_openai_key
   OPENWEATHER_API_KEY=your_weather_key
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start the WebSocket server (port 4000)

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
        "message": "Current weather information...",
        "timestamp": 1234567890,
        "status": "in_progress|completed|error"
    }
}
```

## Architecture

```
├── app/
│   ├── core/         # Core configuration
│   └── tools/        # Weather tools and registry
├── main.py          # Main application
├── contributing.md   # Contributing guide
├── main.py.md       # Main app documentation
├── websocket.md     # WebSocket documentation
└── README.md        # This file
```

## Development

For development guidelines and how to extend the assistant's capabilities, please refer to:
- [Contributing Guide](contributing.md) for adding new tools
- [Main Application Documentation](main.py.md) for core functionality
- [WebSocket Implementation](websocket.md) for real-time features

## Error Handling

The application includes comprehensive error handling:
- Connection errors
- API failures
- Tool execution errors
- WebSocket communication issues

All errors are logged and streamed through WebSocket with appropriate status codes.

## Best Practices

1. **Tool Development**
   - Follow the guidelines in [contributing.md](contributing.md)
   - Maintain consistent error handling
   - Include proper documentation

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