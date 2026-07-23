"""LLMProvider fallback chain tests — Phase 5B.

No network — the chain orchestration logic (order resolution, skip-on-no-key,
retry-on-retryable-failure, abort-on-real-error, exhaustion) is fully
provider-agnostic and testable with small fake LLMProvider stubs.
"""

from __future__ import annotations

import asyncio

import pytest
from app.core.config import Settings
from app.services.llm.base import (
    AllProvidersExhaustedError,
    LLMProvider,
    NoApiKeyConfiguredError,
    ProviderResult,
    ProviderUnavailableError,
)
from app.services.llm.factory import (
    _resolve_provider_order,
    generate_with_fallback,
    transcribe_audio_with_fallback,
)


def _settings(
    *, provider: str = "gemini", fallbacks: str = "", timeout: float = 30.0
) -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://x:x@localhost:5432/x",
        LLM_PROVIDER=provider,
        LLM_FALLBACKS=fallbacks,
        ANTHROPIC_API_KEY=None,
        GEMINI_API_KEY=None,
        GROQ_API_KEY=None,
        OPENROUTER_API_KEY=None,
        LLM_TIMEOUT_SECONDS=timeout,
    )


class _FakeProvider(LLMProvider):
    def __init__(
        self,
        *,
        model: str = "fake-model",
        text: str = "",
        raises: Exception | None = None,
        delay: float = 0,
        supports_audio: bool = False,
    ):
        self.model = model
        self._text = text
        self._raises = raises
        self._delay = delay
        self.supports_audio = supports_audio
        self.called = False

    async def generate(self, *, system_prompt: str, user_content: str) -> str:
        self.called = True
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        return self._text

    async def transcribe_audio(
        self, *, system_prompt: str, audio_bytes: bytes, mime_type: str
    ) -> str:
        self.called = True
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        return self._text


# ── _resolve_provider_order ───────────────────────────────────────────────────


def test_resolve_provider_order_primary_only_when_no_fallbacks():
    settings = _settings(provider="openrouter", fallbacks="")
    assert _resolve_provider_order(settings) == ["openrouter"]


def test_resolve_provider_order_primary_then_fallbacks_in_listed_order():
    settings = _settings(provider="openrouter", fallbacks="gemini,groq,anthropic")
    assert _resolve_provider_order(settings) == ["openrouter", "gemini", "groq", "anthropic"]


def test_resolve_provider_order_deduplicates_primary_from_fallbacks():
    settings = _settings(provider="gemini", fallbacks="gemini,groq")
    assert _resolve_provider_order(settings) == ["gemini", "groq"]


def test_resolve_provider_order_rejects_unknown_primary():
    settings = _settings(provider="bogus", fallbacks="")
    with pytest.raises(ValueError, match="bogus"):
        _resolve_provider_order(settings)


def test_resolve_provider_order_rejects_unknown_fallback():
    settings = _settings(provider="gemini", fallbacks="gemini,bogus")
    with pytest.raises(ValueError, match="bogus"):
        _resolve_provider_order(settings)


# ── generate_with_fallback ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_with_fallback_skips_unconfigured_provider(monkeypatch):
    settings = _settings(provider="gemini", fallbacks="groq")
    unconfigured = _FakeProvider(raises=NoApiKeyConfiguredError("no key"))
    working = _FakeProvider(model="groq-model", text="hello from groq")

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return {"gemini": unconfigured, "groq": working}[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    result = await generate_with_fallback(
        system_prompt="sys", user_content="user", settings=settings
    )
    assert isinstance(result, ProviderResult)
    assert result.provider == "groq"
    assert result.model == "groq-model"
    assert result.text == "hello from groq"
    assert result.latency_seconds >= 0


@pytest.mark.asyncio
async def test_generate_with_fallback_moves_past_retryable_failure(monkeypatch):
    settings = _settings(provider="openrouter", fallbacks="gemini")
    rate_limited = _FakeProvider(raises=ProviderUnavailableError("rate limited"))
    working = _FakeProvider(model="gemini-model", text="hello from gemini")

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return {"openrouter": rate_limited, "gemini": working}[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    result = await generate_with_fallback(
        system_prompt="sys", user_content="user", settings=settings
    )
    assert result.provider == "gemini"
    assert result.text == "hello from gemini"


@pytest.mark.asyncio
async def test_generate_with_fallback_aborts_immediately_on_non_retryable_error(monkeypatch):
    settings = _settings(provider="openrouter", fallbacks="gemini")
    bad_request = _FakeProvider(raises=ValueError("malformed request"))
    never_called = _FakeProvider(model="gemini-model", text="should not be reached")

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return {"openrouter": bad_request, "gemini": never_called}[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    with pytest.raises(ValueError, match="malformed request"):
        await generate_with_fallback(system_prompt="sys", user_content="user", settings=settings)
    assert never_called.called is False


@pytest.mark.asyncio
async def test_generate_with_fallback_raises_when_all_providers_exhausted(monkeypatch):
    settings = _settings(provider="openrouter", fallbacks="gemini,groq")
    exhausted = {
        "openrouter": _FakeProvider(raises=ProviderUnavailableError("down")),
        "gemini": _FakeProvider(raises=NoApiKeyConfiguredError("no key")),
        "groq": _FakeProvider(raises=ProviderUnavailableError("down")),
    }

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return exhausted[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    with pytest.raises(AllProvidersExhaustedError):
        await generate_with_fallback(system_prompt="sys", user_content="user", settings=settings)


@pytest.mark.asyncio
async def test_generate_with_fallback_skips_a_hung_provider_and_moves_on(monkeypatch):
    # Regression: no provider is constructed with an SDK-level timeout (SDK
    # defaults run ~600s), and this call runs inside run_scheduled_tick while
    # holding the scheduler's advisory lock — a hung call must not block every
    # company's dispatch for minutes. A timeout is treated like
    # ProviderUnavailableError: skip to the next provider.
    settings = _settings(provider="gemini", fallbacks="groq", timeout=0.05)
    hung = _FakeProvider(delay=1.0, text="too late")
    working = _FakeProvider(model="groq-model", text="hello from groq")

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return {"gemini": hung, "groq": working}[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    result = await generate_with_fallback(
        system_prompt="sys", user_content="user", settings=settings
    )
    assert result.provider == "groq"
    assert result.text == "hello from groq"


@pytest.mark.asyncio
async def test_generate_with_fallback_skips_blank_response_and_moves_on(monkeypatch):
    # Regression: Gemini's response.text is None (no exception raised) on a
    # safety-blocked or empty-candidate response. Treating that as "success"
    # crashed briefing.py's find_unverified_amounts(None, ...) downstream with
    # a healthy fallback provider never even tried.
    settings = _settings(provider="gemini", fallbacks="groq")
    blocked = _FakeProvider(text=None)
    working = _FakeProvider(model="groq-model", text="hello from groq")

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return {"gemini": blocked, "groq": working}[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    result = await generate_with_fallback(
        system_prompt="sys", user_content="user", settings=settings
    )
    assert result.provider == "groq"
    assert result.text == "hello from groq"


@pytest.mark.asyncio
async def test_generate_with_fallback_raises_when_every_provider_returns_blank(monkeypatch):
    settings = _settings(provider="gemini", fallbacks="groq")
    all_blank = {
        "gemini": _FakeProvider(text=None),
        "groq": _FakeProvider(text="   "),
    }

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return all_blank[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    with pytest.raises(AllProvidersExhaustedError):
        await generate_with_fallback(system_prompt="sys", user_content="user", settings=settings)


# ── transcribe_audio_with_fallback ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcribe_audio_skips_a_non_audio_capable_provider(monkeypatch):
    # Same restraint as extract_invoice_image_with_fallback's supports_vision
    # gate — a provider with supports_audio=False is skipped exactly like a
    # missing API key, never actually called.
    settings = _settings(provider="openrouter", fallbacks="gemini")
    text_only = _FakeProvider(supports_audio=False, text="should never be reached")
    audio_capable = _FakeProvider(
        model="gemini-model", text="record payment", supports_audio=True
    )

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return {"openrouter": text_only, "gemini": audio_capable}[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    result = await transcribe_audio_with_fallback(
        system_prompt="sys", audio_bytes=b"fake", mime_type="audio/ogg", settings=settings
    )
    assert result.provider == "gemini"
    assert result.text == "record payment"
    assert text_only.called is False


@pytest.mark.asyncio
async def test_transcribe_audio_moves_past_retryable_failure(monkeypatch):
    settings = _settings(provider="gemini", fallbacks="groq")
    rate_limited = _FakeProvider(
        supports_audio=True, raises=ProviderUnavailableError("rate limited")
    )
    working = _FakeProvider(model="groq-model", text="hello", supports_audio=True)

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return {"gemini": rate_limited, "groq": working}[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    result = await transcribe_audio_with_fallback(
        system_prompt="sys", audio_bytes=b"fake", mime_type="audio/ogg", settings=settings
    )
    assert result.provider == "groq"
    assert result.text == "hello"


@pytest.mark.asyncio
async def test_transcribe_audio_raises_when_no_audio_capable_provider_configured(monkeypatch):
    settings = _settings(provider="openrouter", fallbacks="groq")
    text_only_a = _FakeProvider(supports_audio=False)
    text_only_b = _FakeProvider(supports_audio=False)

    def fake_build(name: str, _settings: Settings) -> LLMProvider:
        return {"openrouter": text_only_a, "groq": text_only_b}[name]

    monkeypatch.setattr("app.services.llm.factory._build_provider", fake_build)

    with pytest.raises(AllProvidersExhaustedError):
        await transcribe_audio_with_fallback(
            system_prompt="sys", audio_bytes=b"fake", mime_type="audio/ogg", settings=settings
        )
