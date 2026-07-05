from functools import lru_cache

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="OpsGenie", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/opsgenie",
        alias="DATABASE_URL",
    )

    # Phase 6 — shared-key auth for every /admin/* route (see app/core/auth.py).
    # None until set in .env; require_api_key fails closed (401) when unset,
    # rather than silently allowing unauthenticated traffic through.
    admin_api_key: str | None = Field(default=None, alias="ADMIN_API_KEY")

    # Phase 7 — WhatsApp inbound webhook (see app/api/webhooks/whatsapp.py).
    # whatsapp_verify_token is Meta's GET handshake secret; whatsapp_app_secret
    # signs every POST body (X-Hub-Signature-256). Both fail closed when unset,
    # same convention as admin_api_key.
    whatsapp_verify_token: str | None = Field(default=None, alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_app_secret: str | None = Field(default=None, alias="WHATSAPP_APP_SECRET")

    # Phase 8 — outbound sending (see app/services/whatsapp_client.py). Both
    # fail closed (WhatsAppNotConfiguredError) when unset, same convention.
    whatsapp_token: str | None = Field(default=None, alias="WHATSAPP_TOKEN")
    whatsapp_phone_number_id: str | None = Field(default=None, alias="WHATSAPP_PHONE_NUMBER_ID")

    # Phase 10 — NotificationEngine's two founder-facing ops alerts ("no data
    # received in 24h", "briefing delivery failed") go to the OpsGenie
    # operator's own number, distinct from any distributor's whatsapp_number.
    # None until set; those two alerts are simply skipped (logged) when unset.
    founder_whatsapp_number: str | None = Field(default=None, alias="FOUNDER_WHATSAPP_NUMBER")

    # Self-serve onboarding (see app/api/onboarding.py). The public /onboard
    # page is gated by this shared access code — fail-closed like admin_api_key
    # (onboarding rejects everything when unset). welcome_template_* name the
    # Meta-approved template pushed when a company's subscription is activated
    # (a free-form welcome to a never-seen number is blocked by WhatsApp's 24h
    # rule, so it must be a template).
    onboarding_access_code: str | None = Field(default=None, alias="ONBOARDING_ACCESS_CODE")
    welcome_template_name: str | None = Field(default=None, alias="WELCOME_TEMPLATE_NAME")
    welcome_template_language: str = Field(default="en_US", alias="WELCOME_TEMPLATE_LANGUAGE")

    # Phase 11 — APScheduler (see app/core/scheduler.py). One poll job ticks
    # every scheduler_poll_interval_minutes and, per company, acts when the
    # company's own business-local hour matches these targets. NotificationEngine
    # rules run every tick and dedup internally, so no separate interval is
    # needed. Defaults to False (fail-closed, like admin_api_key/whatsapp_token)
    # so an accidental boot never fires real WhatsApp sends — a real deployment
    # must set SCHEDULER_ENABLED=true explicitly.
    scheduler_enabled: bool = Field(default=False, alias="SCHEDULER_ENABLED")
    scheduler_poll_interval_minutes: int = Field(
        default=15, alias="SCHEDULER_POLL_INTERVAL_MINUTES"
    )
    briefing_hour: int = Field(default=8, alias="BRIEFING_HOUR")
    briefing_retry_hour: int = Field(default=9, alias="BRIEFING_RETRY_HOUR")
    followup_hour: int = Field(default=10, alias="FOLLOWUP_HOUR")

    # AI (Phase 5B) — BriefingService narration layer only, via app.services.llm's
    # pluggable LLMProvider + automatic failover chain. llm_provider is the
    # primary; llm_fallbacks (comma-separated, e.g. "gemini,groq,anthropic")
    # is tried in order if the primary fails retryably. Any subset of the 4
    # providers' credentials can be populated at once without conflict — a
    # provider with no key configured is skipped silently by the chain, never
    # silently proceeding with a missing key on the one it does try.
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_fallbacks: str = Field(default="", alias="LLM_FALLBACKS")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-haiku-4-5", alias="ANTHROPIC_MODEL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openai/gpt-oss-120b:free", alias="OPENROUTER_MODEL")

    # Agentic WhatsApp assistant: max tool-call rounds per message (loop guard),
    # and how many prior dialogue turns to load as multi-turn memory.
    agent_max_steps: int = Field(default=5, alias="AGENT_MAX_STEPS")
    agent_history_turns: int = Field(default=10, alias="AGENT_HISTORY_TURNS")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        allowed_schemes = (
            "postgresql+asyncpg://",
            "postgres+asyncpg://",
        )
        if not value.startswith(allowed_schemes):
            raise ValueError(
                "DATABASE_URL must use the asyncpg driver "
                "(postgresql+asyncpg:// or postgres+asyncpg://)."
            )
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
