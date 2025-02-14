import json
import time
import asyncio
import websockets
from openai import OpenAI, AssistantEventHandler, OpenAIError
from app.tools.registry import registry
from app.tools.weather import WeatherTool
from app.core.config import settings

# Initialize OpenAI client with direct API key
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# WebSocket configuration
WEBSOCKET_URI = "ws://localhost:4000"
WEBSOCKET_CHANNEL = "weather-update"

class WebSocketManager:
    def __init__(self, uri, channel):
        self.uri = uri
        self.channel = channel
        self.websocket = None
        self.is_subscribed = False
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.uri)
            # Subscribe to the channel
            subscribe_message = {
                "type": "subscribe",
                "payload": {
                    "channel": self.channel
                }
            }
            await self.websocket.send(json.dumps(subscribe_message))
            
            # Wait for subscription confirmation
            response = await self.websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("type") == "subscribed":
                self.is_subscribed = True
                print(f"\nSuccessfully subscribed to channel: {self.channel}")
            else:
                print(f"\nFailed to subscribe to channel: {self.channel}")
                
        except Exception as e:
            print(f"\nError connecting to WebSocket: {str(e)}")
            self.websocket = None

    async def send_message(self, message_data):
        if self.websocket and self.is_subscribed:
            try:
                message = {
                    "type": self.channel,
                    "payload": message_data
                }
                print(f"\nAttempting to send message: {json.dumps(message)}")
                await self.websocket.send(json.dumps(message))
                print(f"\nMessage sent successfully")
            except Exception as e:
                print(f"\nError sending WebSocket message: {str(e)}")

    async def disconnect(self):
        if self.websocket and self.is_subscribed:
            try:
                unsubscribe_message = {
                    "type": "unsubscribe",
                    "payload": {
                        "channel": self.channel
                    }
                }
                await self.websocket.send(json.dumps(unsubscribe_message))
                
                # Wait for unsubscribe confirmation
                response = await self.websocket.recv()
                response_data = json.loads(response)
                
                if response_data.get("type") == "unsubscribed":
                    self.is_subscribed = False
                    print(f"\nSuccessfully unsubscribed from channel: {self.channel}")
                
                await self.websocket.close()
                
            except Exception as e:
                print(f"\nError disconnecting from WebSocket: {str(e)}")

# Initialize WebSocket manager
ws_manager = WebSocketManager(WEBSOCKET_URI, WEBSOCKET_CHANNEL)

# Initialize and register tools
weather_tool = WeatherTool(settings.OPENWEATHER_API_KEY)
registry.register(weather_tool)

ASSISTANT_ID = settings.OPENAI_ASSISTANT_ID
OPENAI_MODEL = settings.OPENAI_MODEL

print(f"OPENAI_ASSISTANT_ID: {ASSISTANT_ID}")
print(f"OPENAI_MODEL: {OPENAI_MODEL}")
print(f"OPENWEATHER_API_KEY: {settings.OPENWEATHER_API_KEY}")
print(f"OPENAI_API_KEY: {settings.OPENAI_API_KEY}")

# Get function definitions from our registry
function_definitions = registry.get_function_definitions()

assistant = client.beta.assistants.create(
    model=OPENAI_MODEL,
    name="My Assistant",
    tools=[{"type": "function", "function": func} for func in function_definitions],
    instructions="""I am Kuya Kim, your friendly weather expert! I specialize in 
    providing accurate weather updates with a dash of humor. I'll always use my 
    weather tools to give you the most up-to-date information about any city's 
    weather conditions. While I can't help with other topics, I promise to make 
    our weather discussions engaging and fun! Just ask me about the weather 
    anywhere in the world, and I'll be happy to help. And yes, even though 
    I'm focused on weather, I might throw in a weather-related joke or 
    two to brighten your day!""",
)

def create_thread():
    return client.beta.threads.create()

def create_message(thread_id, message):
   return client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)

class MyEventHandler(AssistantEventHandler):
    def __init__(self, websocket_manager, loop=None):
        super().__init__()
        self._stream = None
        self.message_content = ""
        self.loop = loop
        self.current_thread_id = None
        self.current_run_id = None
        self.is_complete = False
        self.ws_manager = websocket_manager
        if loop:
            self.ws_manager.set_loop(loop)

    def on_event(self, event):
        print(f"\nReceived event: {event.event}")  # Debug print
        
        if event.event == 'thread.run.requires_action':
            self.current_thread_id = event.data.thread_id
            self.current_run_id = event.data.id
            self.handle_tool_calls(event.data)
        elif event.event == 'thread.message.delta':
            time.sleep(0.05) # delay to allow the message to be sent
            if hasattr(event.data.delta, 'content') and event.data.delta.content:
                content = event.data.delta.content[0].text.value
                self.message_content += content
                
                message_data = {
                    "message": self.message_content,
                    "timestamp": time.time(),
                    "status": "in_progress"
                }
                
                if self.loop:
                    print(f"\nSending message via WebSocket: {json.dumps(message_data)}")
                    self.loop.run_until_complete(self.ws_manager.send_message(message_data))
                else:
                    print("\nWarning: No event loop available for WebSocket message")

        elif event.event == 'thread.message.completed':
            if hasattr(event.data, 'content') and event.data.content:
                print("\nMessage completed, sending final message")
                if self.loop:
                    final_message = {
                        "message": self.message_content,
                        "timestamp": time.time(),
                        "status": "completed",
                    }
                    self.loop.run_until_complete(self.ws_manager.send_message(final_message))
                else:
                    print("\nWarning: No event loop available for final message")

        elif event.event == 'thread.run.completed':
            print("\nRun completed deleting assistant.")
            client.beta.assistants.delete(assistant.id)
            self.is_complete = True

    def handle_tool_calls(self, data):
        tool_outputs = []
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            try:
                arguments = json.loads(tool.function.arguments)
                print(f"\nExecuting function: {tool.function.name} with arguments: {arguments}")
                
                result = self.loop.run_until_complete(
                    registry.execute_function(tool.function.name, arguments)
                )
                print(f"Function result: {result}")
                
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": json.dumps(result) if result is not None else "null"
                })
            except Exception as e:
                print(f"Error executing function: {str(e)}")
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": f"Error executing function: {str(e)}"
                })
        
        print("\nSubmitting tool outputs:", tool_outputs)
        self.submit_tool_outputs(tool_outputs)

    def submit_tool_outputs(self, tool_outputs):
        try:
            if self.current_thread_id and self.current_run_id:
                # Create new event handler with the same loop
                new_handler = MyEventHandler(self.ws_manager, self.loop)
                
                with client.beta.threads.runs.submit_tool_outputs_stream(
                    thread_id=self.current_thread_id,
                    run_id=self.current_run_id,
                    tool_outputs=tool_outputs,
                    event_handler=new_handler,
                ) as stream:
                    stream.until_done()
                print("\nTool outputs submitted successfully")
            else:
                print("\nError: Missing thread_id or run_id")
        except Exception as e:
            print(f"\nError submitting tool outputs: {str(e)}")

    def on_error(self, error):
        print(f"\nError in event handler: {error}")
        if self.loop and self.ws_manager:
            try:
                error_message = {
                    "message": "I encountered an issue while processing your request. Please try again.",
                    "friendly_message": str(error),
                    "timestamp": time.time(),
                    "status": "error",
                    "type": "error"
                }
                print(f"\nSending error message to WebSocket: {json.dumps(error_message)}")
                self.loop.run_until_complete(self.ws_manager.send_message(error_message))
            except Exception as e:
                print(f"\nError sending error message to WebSocket: {str(e)}")

def run_conversation():
    # Create and initialize event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Initialize event handler with WebSocket manager and loop
    event_handler = MyEventHandler(ws_manager, loop)
    
    try:
        # Initialize WebSocket connection
        loop.run_until_complete(ws_manager.connect())
        
        thread = create_thread()
        print(f"\nCreated thread: {thread.id}")
        
        message = create_message(thread.id, "Is it raining in Makati?")
        print(f"Created message: {message.id}")
        
        print("\nStarting conversation stream...")
        
        # Create and stream the run
        with client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=assistant.id,
            event_handler=event_handler,
        ) as stream:
            # The run ID will be available in the event handler after the first event
            stream.until_done()
            
    except Exception as e:
        print(f"\nError in conversation: {str(e)}")
    finally:
        # Cleanup WebSocket connection
        if loop:
            loop.run_until_complete(ws_manager.disconnect())
            loop.close()

if __name__ == "__main__":
    run_conversation()