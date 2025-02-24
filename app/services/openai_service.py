from typing import List, Dict, Any, Tuple
from openai import OpenAI, AssistantEventHandler, NotFoundError
from ..core.config import settings
from ..tools.registry import registry
import time


class OpenAIService:
    def __init__(self):
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

    def create_assistant_id(self, function_definitions: List[Dict[str, Any]]):
        """Create a new OpenAI assistant and return its ID

        Args:
            function_definitions (List[Dict[str, Any]]): List of function definitions for the assistant

        Returns:
            str: The created assistant's ID
        """
        assistant = self.client.beta.assistants.create(
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
        print(f"\n=== ASSISTANT ID ===\n{assistant.id}\n==================\n")
        return assistant.id

    def check_active_runs(self, thread_id: str) -> bool:
        """Check if there are any active runs for a thread

        Args:
            thread_id (str): The thread ID

        Returns:
            bool: True if there are active runs, False otherwise
        """
        try:
            runs = self.client.beta.threads.runs.list(thread_id=thread_id)
            return any(
                run.status in ["queued", "in_progress", "requires_action"]
                for run in runs.data
            )
        except Exception:
            return False

    def create_message(
        self, thread_id: str, message: str, event_handler: AssistantEventHandler = None
    ):
        """Create a new message in a thread

        Args:
            thread_id (str): The ID of the existing thread to add the message to
            message (str): The message content to add
            event_handler (AssistantEventHandler, optional): Event handler for error propagation

        Raises:
            NotFoundError: If the thread_id doesn't exist
            Exception: If thread has active runs
        """
        try:
            # Check for active runs first
            if self.check_active_runs(thread_id):
                error = Exception(
                    "Thread has an active run. Please wait for it to complete before adding new messages."
                )
                if event_handler:
                    event_handler.on_error(error)
                raise error

            return self.client.beta.threads.messages.create(
                thread_id=thread_id, role="user", content=message
            )
        except Exception as e:
            if event_handler:
                event_handler.on_error(e)
            raise

    def delete_assistant(self, assistant_id: str):
        """Delete an assistant

        Args:
            assistant_id (str): The ID of the assistant to delete
        """
        try:
            self.client.beta.assistants.delete(assistant_id)
            print(
                f"\n=== DELETED ASSISTANT ===\n{assistant_id}\n=====================\n"
            )
        except Exception as e:
            print(
                f"\n=== ERROR DELETING ASSISTANT ===\n{str(e)}\n=========================\n"
            )

    def wait_for_run(self, thread_id: str, run_id: str) -> str:
        """Wait for a run to be in a state where we can interact with it

        Args:
            thread_id (str): The thread ID
            run_id (str): The run ID

        Returns:
            str: The current status of the run
        """
        while True:
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run_id
            )
            if run.status not in ["queued", "in_progress"]:
                return run.status
            time.sleep(0.5)  # Short delay between checks

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
        try:
            # Stream the run
            with self.client.beta.threads.runs.stream(
                thread_id=thread_id,
                assistant_id=assistant_id,
                event_handler=event_handler,
            ) as stream:
                stream.until_done()
        except Exception as e:
            # Ensure error is propagated to event handler
            event_handler.on_error(e)
            raise

    def submit_tool_outputs(
        self,
        thread_id: str,
        run_id: str,
        tool_outputs: List[Dict[str, Any]],
        event_handler: AssistantEventHandler,
    ):
        """Submit tool outputs to a run"""
        try:
            # Wait for run to be in a state where we can submit outputs
            status = self.wait_for_run(thread_id, run_id)
            if status not in ["requires_action"]:
                raise Exception(f"Cannot submit tool outputs in run status: {status}")

            # Submit tool outputs
            with self.client.beta.threads.runs.submit_tool_outputs_stream(
                run_id=run_id,
                thread_id=thread_id,
                tool_outputs=tool_outputs,
                event_handler=event_handler,
            ) as stream:
                stream.until_done()
        except Exception as e:
            # Ensure error is propagated to event handler
            event_handler.on_error(e)
            raise

    def create_thread(self):
        """Create a new conversation thread for testing purposes"""
        thread = self.client.beta.threads.create()
        print(f"\n=== TEST THREAD ID ===\n{thread.id}\n=====================\n")
        return thread
