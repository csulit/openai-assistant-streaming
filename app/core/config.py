from pydantic_settings import BaseSettings
from dotenv import load_dotenv, find_dotenv
from typing import Optional
import os
import logging

env_path = find_dotenv(usecwd=True)
if env_path:
    load_dotenv(dotenv_path=env_path, override=True)

logger = logging.getLogger(__name__)

logger.debug("Environment variables before Settings init:")
logger.debug(f"OPENAI_API_KEY from os.environ: {'*' * 8 if 'OPENAI_API_KEY' in os.environ else 'Not set'}")

class Settings(BaseSettings):
    # OpenAI settings
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4-1106-preview"
    OPENAI_ASSISTANT_ID: Optional[str] = None
    OPENAI_ASSISTANT_NAME: str = "Cosmo"
    OPENAI_ASSISTANT_INSTRUCTIONS: str = "You are Cosmo, a helpful AI assistant."

    # Weather API settings
    OPENWEATHER_API_KEY: str

    # WebSocket settings
    WEBSOCKET_URI: str = "ws://localhost:4000"
    WEBSOCKET_HOST: str = "localhost"
    WEBSOCKET_PORT: int = 8765

    # Database settings
    MSSQL_CONNECTION_STRING: str
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "postgres"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"

    # RabbitMQ settings
    RABBITMQ_URL: str = "amqp://user:password@localhost:5672"
    QUEUE_NAME: str = "cosmo_queue"
    ROUTING_KEY: str = "cosmo_routing"
    EXCHANGE_NAME: str = "cosmo_exchange"

    # Environment settings
    NODE_ENV: str = "development"

    # API settings
    X_API_KEY: str = "rbac_test_Rnby1BpI5cr9oT1R27NnWxlu2l0BNAzxceHwrDR0Lr"
    
    # Audit API settings
    AUDIT_API_URL: str = "https://erp-v2-rbac-api-staging.kmcc-app.cc/api/b2b/users/audit-logs"
    
    # User Role API settings
    USER_ROLE_API_URL: str = "https://erp-v2-rbac-api-staging.kmcc-app.cc/api/b2b/users"

    class Config:
        case_sensitive = False
        env_file = ".env"

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

logger.debug("Settings initialized:")
