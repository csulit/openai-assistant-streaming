from typing import List, Dict, Any, Tuple
from openai import OpenAI, AssistantEventHandler, NotFoundError
from ..core.config import settings
from ..tools.registry import registry


class OpenAIService:
    def __init__(self):
        self.assistant = None
        self.model = settings.OPENAI_MODEL
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def check_thread_exists(self, thread_id: str) -> Tuple[bool, str]:
        """Check if a thread exists

        Args:
            thread_id (str): The ID of the thread to check

        Returns:
            Tuple[bool, str]: (exists, error_message)
            - exists: True if thread exists, False otherwise
            - error_message: Error message if thread doesn't exist, empty string otherwise
        """
        try:
            self.client.beta.threads.retrieve(thread_id)
            return True, ""
        except NotFoundError:
            return (
                False,
                "Thread not found. The conversation may have expired or been deleted.",
            )
        except Exception as e:
            return False, f"Error checking thread: {str(e)}"

    def create_assistant(self, function_definitions: List[Dict[str, Any]]):
        """Create a new OpenAI assistant with the given function definitions"""
        self.assistant = self.client.beta.assistants.create(
            model=self.model,
            name="Cosmo",
            tools=[
                {"type": "function", "function": func} for func in function_definitions
            ],
            instructions="""
                You are Cosmo, a professional KMC Solutions staff member with expertise in three specific areas:

                1. Weather Expert (as Kuya Kim):
                - As Cosmo, you channel Kuya Kim's expertise for weather-related queries
                - Provide accurate and engaging weather updates with your signature friendly style
                - Focus on temperature, humidity, wind conditions, and practical advice for the day
                - Make weather information relatable with relevant examples and occasional weather jokes

                2. Business Intelligence Analyst:
                - As Cosmo, you are KMC's go-to analyst for client portfolio insights
                - Present client distribution data with clear insights and business context
                - Always highlight trends and patterns in the client base
                - Maintain a professional, analytical tone while being engaging
                - Focus on actionable insights from the numbers

                3. Sales Solutions Specialist:
                - As Cosmo, you are KMC's experienced office space consultant
                - Help clients find the perfect office space based on their requirements
                - Consider location preferences and team size requirements
                - Provide detailed information about available spaces with a consultative approach
                - Focus on matching client needs with available options

                Core Principles:
                1. Identity and Expertise:
                - You are Cosmo, a valued member of the KMC Solutions team
                - Stay focused on your three areas of expertise
                - Take pride in providing accurate and helpful information
                
                2. Professional Communication:
                - Always introduce yourself as Cosmo when appropriate
                - Weather updates: Channel Kuya Kim's friendly and engaging style
                - Business/Sales queries: Maintain a professional, consultative tone
                - Never say you're an AI or virtual assistant
                - Speak naturally as a knowledgeable professional

                3. Response Guidelines:
                - Begin responses with relevant context
                - Use natural, conversational language
                - Be direct and specific
                - Include relevant details without overwhelming
                - Focus on practical, actionable information
                - Sign off as Cosmo when appropriate

                4. Query Handling:
                - For weather: Provide current conditions with practical implications
                - For client data: Emphasize business insights and trends
                - For office space: Consider both stated and implied requirements
                - If a query is outside your expertise, politely explain what services you can provide as Cosmo

                Remember: You are Cosmo, a trusted KMC Solutions professional. Your responses should reflect your expertise and commitment to providing excellent service to clients and colleagues.
            """,
        )
        return self.assistant

    def create_message(self, thread_id: str, message: str):
        """Create a new message in a thread

        Args:
            thread_id (str): The ID of the existing thread to add the message to
            message (str): The message content to add

        Raises:
            NotFoundError: If the thread_id doesn't exist
        """
        return self.client.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=message
        )

    def delete_assistant(self, assistant_id: str):
        """Delete an assistant"""
        self.client.beta.assistants.delete(assistant_id)

    def stream_conversation(
        self, thread_id: str, assistant_id: str, event_handler: AssistantEventHandler
    ):
        """Stream a conversation with the assistant

        Args:
            thread_id (str): The ID of the existing thread to stream
            assistant_id (str): The ID of the assistant to use
            event_handler (AssistantEventHandler): The event handler for processing responses

        Raises:
            NotFoundError: If the thread_id doesn't exist
        """
        run = self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )

        with self.client.beta.threads.runs.stream(
            thread_id=thread_id,
            run_id=run.id,
            event_handler=event_handler,
        ) as stream:
            stream.until_done()

    def submit_tool_outputs(
        self,
        thread_id: str,
        run_id: str,
        tool_outputs: List[Dict[str, Any]],
        event_handler: AssistantEventHandler,
    ):
        """Submit tool outputs to a run"""
        with self.client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=tool_outputs,
            event_handler=event_handler,
        ) as stream:
            stream.until_done()
