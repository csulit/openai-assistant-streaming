from pydantic_settings import BaseSettings
from dotenv import load_dotenv, find_dotenv

env_path = find_dotenv(usecwd=True)
if env_path:
    load_dotenv(dotenv_path=env_path, override=True)


class Settings(BaseSettings):
    # OpenAI settings
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_ASSISTANT_ID: str = "n/a"

    # Weather API settings
    OPENWEATHER_API_KEY: str

    # WebSocket settings
    WEBSOCKET_URI: str = "wss://erp-v2-cosmo-socket.kmc.solutions/"

    # Database settings
    MSSQL_CONNECTION_STRING: str

    # RabbitMQ settings
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    QUEUE_NAME: str = "cosmo_queue"
    ROUTING_KEY: str = "cosmo.message"
    EXCHANGE_NAME: str = "malcolm"

    # Environment settings
    NODE_ENV: str = "development"

    class Config:
        case_sensitive = False

    def __init__(self, **kwargs):
        # Debug: Print environment variables before initialization
        print("\nDebug - Environment variables before Settings init:")
        print(f"OPENAI_API_KEY from os.environ: {'*' * 8}")

        super().__init__(**kwargs)

        # Debug: Print final values after initialization
        print("\nDebug - Final Settings values:")
        print(f"OPENAI_API_KEY in Settings: {'*' * 8}")
        print(f"WEBSOCKET_URI in Settings: {self.WEBSOCKET_URI}")
        print(
            f"Database connection configured: {'Yes' if self.MSSQL_CONNECTION_STRING else 'No'}"
        )
        print(f"RabbitMQ URL configured: {'Yes' if self.RABBITMQ_URL else 'No'}")


settings = Settings()
