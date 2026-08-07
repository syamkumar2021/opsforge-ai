from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "OpsForge AI"
    app_env: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    secret_key: str
    access_token_expire_minutes: int = 60

    # PostgreSQL
    postgres_user: str = "opsforge"
    postgres_password: str = "opsforge_secret"
    postgres_db: str = "opsforge"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_exceptions: str = "ops.exceptions"
    kafka_topic_dlq: str = "ops.exceptions.dlq"
    kafka_topic_notifications: str = "ops.notifications"
    kafka_consumer_group: str = "opsforge-workers"
    kafka_auto_offset_reset: str = "earliest"

    # LLM (OpenAI-compatible)
    # ======================
    # LLM (OpenRouter - OpenAI compatible)
    # ======================
    openai_api_key: str
    openai_model: str = "meta-llama/llama-3.3-70b-instruct"
    openai_base_url: str = "https://openrouter.ai/api/v1"  # Change to your provider

    # Playwright
    playwright_headless: bool = True
    vendor_portal_url: str = "https://example-vendor-portal.com"
    carrier_tracking_url: str = "https://www.ups.com/track"

    # Future MuleSoft (real connection - currently unused)
    mulesoft_base_url: Optional[str] = None
    mulesoft_client_id: Optional[str] = None
    mulesoft_client_secret: Optional[str] = None
    mulesoft_token_url: Optional[str] = None

    # ======================
    # LangSmith Observability
    # ======================
    langchain_tracing_v2: bool = True
    langchain_api_key: Optional[str] = None
    langchain_project: str = "OpsForge-AI"
    langchain_endpoint: str = "https://api.smith.langchain.com"


    # Email / SMTP
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "opsforge@local.test"
    smtp_tls: bool = False
    notify_email_to: str = "ops-team@company.com"

@lru_cache
def get_settings() -> Settings:
    return Settings()