import os
import re
import sys
import time
import json
from rich.table import Table
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from openai import OpenAI, AssistantEventHandler, OpenAIError

# Load environment variables from the .env file
load_dotenv()

# Initialize OpenAI client with the API key from environment variables
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)

# Initialize Rich for better output formatting and visualization
output_formatter = Console()

# Initialize variables
attachments = []
my_files = []

# Get assistant ID from environment variables starting with "OPENAI_ASSISTANT_ID"
assistant_id = os.getenv("OPENAI_ASSISTANT_ID")

# Get all file IDs from environment variables
# Collect all environment variables starting with "OPENAI_FILE_ID_"
file_ids = {
    key: value for key, value in os.environ.items() if key.startswith("OPENAI_FILE_ID_")
}

# Convert the object with key-value pairs (i.e., dictionary) to an array containing a list of values
file_id_values = list(file_ids.values())

# Display the header and subheader
header = """
<br>

# Terminal user interface for the OpenAI Assistants API v2 beta

##### Made with ❤️  by Rok Benko

<br>
"""
md_header = Markdown(header)
output_formatter.print(md_header)

# Check if assistant ID is added in the .env file and display an error message if not
if not assistant_id:
    output_formatter.print(
        "\nExiting the script[red]...[/red]\nPlease edit the .env file and add the environment variable OPENAI_ASSISTANT_ID. Then run the script again.\n",
        style="red",
    )
    exit(1)

try:
    # Retrieve assistant details
    assistant_details = client.beta.assistants.retrieve(assistant_id=assistant_id)

    # Get assistant name
    if assistant_details.name:
        get_name = assistant_details.name

    # Get assistant instructions
    if assistant_details.instructions:
        get_instructions = assistant_details.instructions

    # Get assistant LLM
    if assistant_details.model:
        get_model = assistant_details.model

    # Get assistant tools
    all_tools = []

    if assistant_details.tools:
        for tool in assistant_details.tools:
            all_tools.append(tool.type)

    # Display assistant details
    output_formatter.print(
        "Assistant found in the .env file", style="on deep_sky_blue1"
    )
    output_formatter.print(f"Assistant: {get_name}", style="deep_sky_blue1")
    output_formatter.print(f"Instructions: {get_instructions}", style="deep_sky_blue1")
    output_formatter.print(f"Tools: {','.join(all_tools)}", style="deep_sky_blue1")
    output_formatter.print(
        f"LLM: [deep_sky_blue1]{get_model}[/deep_sky_blue1]", style="deep_sky_blue1"
    )
except OpenAIError as e:
    # Handle error when retrieving assistant details
    output_formatter.print(
        f"\nExiting the script[red]...[/red]\nError retrieving assistant details:\n{e}\n",
        style="red",
    )
    exit(1)

# Check if file IDs are added in the .env file
if not file_id_values:
    # If no, display a warning message
    output_formatter.print(
        "\nWarning: There are no environment variables starting with OPENAI_FILE_ID_ added in the .env file. Consequently, no files will be added to the assistant.\n",
        style="yellow3",
    )

    # Ask the user if they are okay with no files being added to the assistant
    confirm = input("Are you okay with this? (y/n): ")

    # If no, exit the script
    if confirm.lower() == "n" or confirm.lower() == "no":
        output_formatter.print(
            "\nExiting the script[red]...[/red]\nPlease edit the .env file and add environment variables starting with OPENAI_FILE_ID_. Then run the script again.\n",
            style="red",
        )
        exit(1)
else:
    # If yes, display the files
    output_formatter.print("\nFiles found in the .env file", style="on deep_sky_blue1")

    for value in file_id_values:
        try:
            # Retrieve file details
            file_details = client.files.retrieve(file_id=value)
        except OpenAIError as e:
            # Handle error when retrieving file details
            output_formatter.print(
                f"Exiting the script[red]...[/red]\nError retrieving file details:\n{e}\n",
                style="red",
            )
            exit(1)

        # Get file name
        get_filename = file_details.filename

        # Ask user for the tool
        add_tool = input(
            f"Please add a tool for {get_filename} file (code_interpreter/file_search): "
        )

        # If invalid tool is entered, display an error message
        if add_tool.lower() != "code_interpreter" and add_tool.lower() != "file_search":
            output_formatter.print(
                "\nExiting the script[red]...[/red]\nYou entered an invalid tool. A tool must be either code_interpreter or file_search. Please try again.\n",
                style="red",
            )
            exit(1)

        # Add file details to attachments
        attachments.append(
            {"file_name": get_filename, "file_id": value, "tools": [{"type": add_tool}]}
        )

# If file IDs are added in the .env file
if file_id_values:
    # Generate a table
    table = Table(row_styles=["", "dim"])
    table.add_column("File name", justify="left", style="deep_sky_blue1")
    table.add_column("File ID", justify="left", style="deep_sky_blue1")
    table.add_column("Tool", justify="left", style="deep_sky_blue1")

    for attachment in attachments:
        # Get file name
        get_filename = attachment["file_name"]

        # Get file ID
        get_file_id = attachment["file_id"]
        get_file_id_masked = "file-" + "*" * (len(get_file_id) - 5) + get_file_id[-5:]

        # Get tools
        get_tools = ", ".join(tool["type"] for tool in attachment["tools"])

        table.add_row(get_filename, get_file_id_masked, get_tools)

    # Display the table with file details
    output_formatter.print(table)


# Define class for handling streaming events
class MyEventHandler(AssistantEventHandler):
    def __init__(self):
        super().__init__()  # Call parent class init to properly initialize
        self._stream = None  # Initialize the stream attribute that parent class expects
        self.message_content = ""

    def on_event(self, event):
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id
            self.handle_requires_action(event.data, run_id)
        elif event.event == 'thread.message.delta':
            time.sleep(0.05)  # Add 50ms delay between characters
            self.message_content += event.data.delta.content[0].text.value
            output_formatter.print(event.data.delta.content[0].text.value, end="", style="black on white")
        elif event.event == 'thread.message.completed':
            self.message_content = event.data.content[0].text.value
        elif event.event == 'thread.run.completed':
            self.message_content = ""
            
    def handle_requires_action(self, data, run_id):
        tool_outputs = []
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "get_weather":
                arguments = json.loads(tool.function.arguments)
                print(arguments)
                tool_outputs.append({"tool_call_id": tool.id, "output": "It is cloudy in makati but no chance of rain."})
        
        print("\nTool outputs: ", tool_outputs)

        # Submit all tool_outputs at the same time
        self.submit_tool_outputs(tool_outputs, run_id)
 
    def submit_tool_outputs(self, tool_outputs, run_id):
        with client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=self.current_run.thread_id,
            run_id=self.current_run.id,
            tool_outputs=tool_outputs,
            event_handler=MyEventHandler(),
        ) as stream:
            stream.until_done()

    def on_error(self, error):
        self.message_content = ""
        print(error)

try:
    # Step 1: Create a new thread
    my_thread = client.beta.threads.create()
except OpenAIError as e:
    # Handle error when creating a new thread
    output_formatter.print(
        f"\nExiting the script[red]...[/red]\nError creating a new thread:\n{e}\n",
        style="red",
    )
    exit(1)

# Loop until the user enters "quit"
while True:
    # Step 2: Get the user question and display it
    print("")
    user_question = input("User: ")

    # Check if the user wants to quit the chat
    if user_question.lower() == "quit":
        output_formatter.print(
            "\nAssistant: Have a nice day! :wave:\n", style="black on white"
        )
        break

    try:
        # Check if file IDs are added in the .env file
        if not file_id_values:
            # If no, don't add the attachments parameter
            # Step 3: Add the user question to the thread messages
            my_thread_message = client.beta.threads.messages.create(
                thread_id=my_thread.id,
                role="user",
                content=user_question,
            )
        else:
            # If yes, add the attachments parameter
            # Iterate over attachments
            for attachment in attachments:
                file_id = attachment["file_id"]
                tools = attachment["tools"]

                # Construct the attachment object with key-value pairs (i.e., dictionary)
                attachment_object = {"file_id": file_id, "tools": tools}

                # Append the constructed attachment to 'my_files'
                my_files.append(attachment_object)

            # Step 3: Add the user question to the thread messages
            my_thread_message = client.beta.threads.messages.create(
                thread_id=my_thread.id,
                role="user",
                content=user_question,
                attachments=my_files,  # Change from v1 to v2 beta: Messages have the attachments parameter instead of the file_ids parameter
            )
    except OpenAIError as e:
        # Handle error when adding the user question to the thread messages
        output_formatter.print(
            f"\nExiting the script[red]...[/red]\nError adding the user question to thread messages:\n{e}\n",
            style="red",
        )
        exit(1)

    try:
        # Step 4: Run the assistant and stream its answer
        with client.beta.threads.runs.stream(
            thread_id=my_thread.id,
            assistant_id=assistant_id,
            event_handler=MyEventHandler(),
        ) as stream:
            stream.until_done()
    except OpenAIError as e:
        # Handle error when running and streaming the assistant answer
        output_formatter.print(
            f"\nExiting the script[red]...[/red]\nError running and streaming the assistant answer:\n{e}\n",
            style="red",
        )
        exit(1)

