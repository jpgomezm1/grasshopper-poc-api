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

    # Bitrix CRM integration (GH-S10 · D-020 stub default · activation in S12)
    # If BITRIX_WEBHOOK_URL is empty → bitrix_client operates in stub mode
    # (logs payloads, returns synthetic IDs, marks provider=stub in sync log).
    # BITRIX_INBOUND_SECRET is the HMAC secret for /webhooks/bitrix/inbound.
    # BITRIX_INBOUND_ENABLED gates the inbound webhook (501 when disabled).
    # BITRIX_NOTIFY_EMAIL receives failure notifications after N retries.
    # BITRIX_RATE_LIMIT_RPS caps outbound calls (Bitrix REST default ~2 r/s).
    bitrix_webhook_url: str = ""
    bitrix_user_token: str = ""
    bitrix_inbound_secret: str = ""
    bitrix_inbound_enabled: bool = False
    # Bitrix24 official webhooks send `application_token` in form-data body
    # (apidocs.bitrix24.com/api-reference/events). When this is set we accept
    # form-urlencoded inbound and validate against application_token instead
    # of the legacy HMAC `X-Hopper-Signature` (kept for proxy/test flows).
    bitrix_application_token: str = ""
    bitrix_notify_email: str = ""
    bitrix_rate_limit_rps: float = 2.0
    bitrix_max_attempts: int = 4
    # Allow tests to short-circuit retries (seconds) · production keeps tenacity defaults.
    bitrix_retry_min_wait_s: float = 2.0
    bitrix_retry_max_wait_s: float = 128.0

    # Sentry (GH-S11-INFRA-01 · DSN empty → no-op SDK)
    sentry_dsn_backend: str = ""
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.05
    sentry_release: str = ""

    # Rate limiting (GH-S11-INFRA-04 · slowapi · per-IP defaults)
    rate_limit_enabled: bool = True
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "3/minute"
    rate_limit_invitations_accept: str = "10/minute"
    rate_limit_programs_import: str = "5/hour"
    rate_limit_external_test_upload: str = "10/hour"
    rate_limit_reports_send: str = "5/hour"
    rate_limit_default: str = "120/minute"

    # Security headers (GH-S11-INFRA-05 · HSTS · CSP · X-Frame-Options · etc.)
    security_headers_enabled: bool = True
    # comma-separated extra connect-src hosts (e.g. "https://api.openai.com")
    csp_extra_connect_src: str = ""

    # Webhook replay protection (GH-S11 · hardening S10)
    webhook_timestamp_tolerance_s: int = 300  # 5 min
    webhook_nonce_ttl_s: int = 600  # 10 min

    # Bitrix inbound webhook payload cap (GH-S11.5-BE-10 · DoS mitigation)
    # Real Bitrix event payloads are well under 50 KB; 1 MB is a generous ceiling.
    # Set to 0 to disable the cap (not recommended in production).
    bitrix_max_payload_kb: int = 1024  # 1 MB default

    # Structured logging (GH-S11 · structlog)
    log_format: str = "json"  # "json" | "console"
    log_level: str = "INFO"

    # Application version (GH-S11 · health check + Sentry release)
    app_version: str = "1.0.0"

    # Habeas Data · privacy policy versioning (GH-S11.5-BE-07 · D-026)
    # Bump when policy text changes materially → forces re-acceptance.
    privacy_policy_version: str = "1.0.0"
    privacy_dpo_email: str = "privacidad@grasshopper.co"

    # SLA thresholds (GH-COMMPROD-B4 · gh_commercial productivity sprint)
    # `pending` for >N hours → breach · `contacted` for >N days → breach ·
    # `qualified` for >N days → breach. UI warning at ~70% of threshold.
    sla_pending_breach_hours: int = 24
    sla_contacted_breach_days: int = 7
    sla_qualified_breach_days: int = 14

    # Web Push (GH-COMMPROD-A2)
    # Generate VAPID keys with `npx web-push generate-vapid-keys` ·
    # empty disables push fan-out (in-app notifications still work).
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:ops@grasshopper.app"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
