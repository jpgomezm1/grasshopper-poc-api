from pydantic_settings import BaseSettings
from pydantic import computed_field
from functools import lru_cache
import os

# Default CORS origins for development
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8080",
    "http://localhost:8081",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8081",
]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://localhost/grasshopper"

    # Anthropic API
    anthropic_api_key: str = ""

    # OpenAI API (for Whisper transcription)
    openai_api_key: str = ""

    # Environment
    environment: str = "development"

    # CORS - comma-separated string from env var
    cors_origins_str: str = ""

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_origins_str:
            return [origin.strip() for origin in self.cors_origins_str.split(',') if origin.strip()]
        return DEFAULT_CORS_ORIGINS

    # AI Settings
    # D-013 (Sprint 5) · pinned to claude-sonnet-4-5 across the project ·
    # the older Haiku-3 referenced by the POC is deprecated for our uses.
    # .env can still override AI_MODEL for short-term experimentation.
    ai_model: str = "claude-sonnet-4-5"
    ai_max_tokens: int = 1024
    ai_temperature: float = 0.7

    # JWT Authentication
    jwt_secret_key: str = "grasshopper-poc-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Storage (GH-S3-INFRA-04 · D-010 Supabase Storage)
    # In S3 these stay empty so storage_service.py uses the stub backend.
    # Real values land in S12 alongside Heroku/Netlify cutover.
    storage_backend: str = ""  # "supabase" | "stub" · auto if empty
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_storage_bucket: str = "grasshopper-uploads"

    # Email transactional (GH-S7 · D-016 Resend default + stub fallback)
    # In S7 these stay empty so email_service.py uses the stub backend.
    # Real provisioning (Resend API key + DKIM/SPF + verified domain) lands in S12.
    resend_api_key: str = ""
    email_from: str = "Grasshopper <hola@grasshopper.co>"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
