"""
Core configuration module using Pydantic settings.
Loads environment variables and validates configuration.
"""
from enum import Enum
from typing import Optional

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentEnum(str, Enum):
    """Environment types."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProviderEnum(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    MISTRAL = "mistral"
    OPENROUTER = "openrouter"
    LOCAL = "local"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ============================================================
    # APPLICATION
    # ============================================================
    ENV: EnvironmentEnum = Field(default=EnvironmentEnum.DEVELOPMENT)
    DEBUG: bool = Field(default=True)
    LOG_LEVEL: str = Field(default="INFO")
    APP_NAME: str = Field(default="Workload Management MCP")
    APP_VERSION: str = Field(default="0.1.0")

    # ============================================================
    # API
    # ============================================================
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    API_WORKERS: int = Field(default=4)

    # ============================================================
    # DATABASE
    # ============================================================
    DATABASE_URL: str = Field(default="postgresql+asyncpg://user:pass@localhost/dbname")
    DATABASE_POOL_SIZE: int = Field(default=20)
    DATABASE_MAX_OVERFLOW: int = Field(default=10)
    DATABASE_ECHO: bool = Field(default=False)

    # ============================================================
    # REDIS
    # ============================================================
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_TTL: int = Field(default=86400)  # 24 hours

    # ============================================================
    # JWT & SECURITY
    # ============================================================
    JWT_SECRET_KEY: str = Field(default="your-super-secret-key-change-in-prod")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRATION_HOURS: int = Field(default=24)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)

    # ============================================================
    # GOOGLE OAUTH
    # ============================================================
    GOOGLE_CLIENT_ID: str = Field(default="")
    GOOGLE_CLIENT_SECRET: str = Field(default="")
    GOOGLE_REDIRECT_URI: str = Field(default="http://localhost:8000/api/v1/auth/google/callback")

    # ============================================================
    # SLACK OAUTH
    # ============================================================
    SLACK_CLIENT_ID: str = Field(default="")
    SLACK_CLIENT_SECRET: str = Field(default="")
    SLACK_REDIRECT_URI: str = Field(default="http://localhost:8000/api/v1/auth/slack/callback")
    SLACK_BOT_TOKEN: str = Field(default="")

    # ============================================================
    # JIRA OAUTH
    # ============================================================
    JIRA_CLIENT_ID: str = Field(default="")
    JIRA_CLIENT_SECRET: str = Field(default="")
    JIRA_REDIRECT_URI: str = Field(default="http://localhost:8000/api/v1/auth/jira/callback")

    # ============================================================
    # LLM PROVIDERS
    # ============================================================
    LLM_PROVIDER: LLMProviderEnum = Field(default=LLMProviderEnum.OPENAI)
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL: str = Field(default="gpt-4-turbo-preview")
    ANTHROPIC_API_KEY: str = Field(default="")
    ANTHROPIC_MODEL: str = Field(default="claude-3-opus-20240229")
    GROQ_API_KEY: str = Field(default="")
    GROQ_MODEL: str = Field(default="llama-3.1-70b-versatile")
    MISTRAL_API_KEY: str = Field(default="")
    MISTRAL_MODEL: str = Field(default="mistral-large-latest")
    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_MODEL: str = Field(default="openai/gpt-4o-mini")

    # ============================================================
    # BACKGROUND JOBS
    # ============================================================
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")
    DRAMATIQ_BROKER: str = Field(default="redis")

    # ============================================================
    # OBSERVABILITY
    # ============================================================
    SENTRY_DSN: Optional[str] = Field(default=None)
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(default=None)
    PROMETHEUS_METRICS_ENABLED: bool = Field(default=True)
    PROMETHEUS_PORT: int = Field(default=9090)

    # ============================================================
    # INTEGRATIONS & SYNC
    # ============================================================
    SYNC_INTERVAL_HOURS: int = Field(default=1)
    GMAIL_BATCH_SIZE: int = Field(default=100)
    SLACK_BATCH_SIZE: int = Field(default=50)
    JIRA_BATCH_SIZE: int = Field(default=50)
    CALENDAR_BATCH_SIZE: int = Field(default=100)

    # ============================================================
    # ENCRYPTION
    # ============================================================
    ENCRYPTION_KEY: str = Field(default="default-encryption-key-change-in-prod")

    # ============================================================
    # FEATURE FLAGS
    # ============================================================
    FEATURE_AI_EXTRACTION: bool = Field(default=True)
    FEATURE_SCHEDULING: bool = Field(default=True)
    FEATURE_WORKLOAD_DETECTION: bool = Field(default=True)
    FEATURE_OVERLOAD_ALERTS: bool = Field(default=True)

    # ============================================================
    # CORS & SECURITY
    # ============================================================
    ALLOWED_ORIGINS: str = Field(default="http://localhost:3000,http://localhost:8000")
    ALLOWED_HOSTS: str = Field(default="localhost,127.0.0.1")

    # ============================================================
    # MCP
    # ============================================================
    MCP_SERVER_PROTOCOL: str = Field(default="stdio")
    MCP_REQUEST_TIMEOUT_SECONDS: int = Field(default=300)

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENV == EnvironmentEnum.PRODUCTION

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.ENV == EnvironmentEnum.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        """Check if running in testing."""
        return self.DEBUG is True and self.ENV != EnvironmentEnum.PRODUCTION

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse allowed origins from comma-separated string."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @property
    def allowed_hosts_list(self) -> list[str]:
        """Parse allowed hosts from comma-separated string."""
        return [host.strip() for host in self.ALLOWED_HOSTS.split(",")]


# Global settings instance
settings = Settings()
