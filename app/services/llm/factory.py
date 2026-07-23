"""generate_with_fallback() — the only public entry point external callers
(BriefingService) need. Resolves the provider order from config
(LLM_PROVIDER + LLM_FALLBACKS, no hardcoded canonical list), then tries each
in order: skip silently on missing key, log and move on for a retryable
failure, abort immediately on anything else (a real bug or bad credential
that another provider can't fix).
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import Settings, get_settings
from app.services.llm.base import (
    AllProvidersExhaustedError,
    AudioTranscriptionUnsupportedError,
    LLMProvider,
    NoApiKeyConfiguredError,
    ProviderResult,
    ProviderUnavailableError,
    VisionUnsupportedError,
)
from app.services.llm.claude_provider import ClaudeProvider
from app.services.llm.cohere_provider import CohereProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.github_models_provider import GitHubModelsProvider
from app.services.llm.groq_provider import GroqProvider
from app.services.llm.openrouter_provider import OpenRouterProvider

logger = logging.getLogger(__name__)

_KNOWN_PROVIDERS = {
    "anthropic",
    "gemini",
    "groq",
    "openrouter",
    "github_models",
    "cohere",
}


def _build_provider(name: str, settings: Settings) -> LLMProvider:
    if name == "anthropic":
        return ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    if name == "gemini":
        return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if name == "groq":
        return GroqProvider(api_key=settings.groq_api_key, model=settings.groq_model)
    if name == "openrouter":
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key, model=settings.openrouter_model
        )
    if name == "github_models":
        return GitHubModelsProvider(
            api_key=settings.github_models_api_key, model=settings.github_models_model
        )
    if name == "cohere":
        return CohereProvider(api_key=settings.cohere_api_key, model=settings.cohere_model)
    raise ValueError(
        f"Unknown LLM provider {name!r}. Expected one of: {', '.join(sorted(_KNOWN_PROVIDERS))}."
    )


def _resolve_provider_order(settings: Settings) -> list[str]:
    """Order comes entirely from config: primary (LLM_PROVIDER) first, then
    LLM_FALLBACKS in the listed order, deduplicated. No hardcoded canonical
    list — an empty LLM_FALLBACKS means no automatic fallback at all.
    """
    primary = settings.llm_provider.strip().lower()
    if primary not in _KNOWN_PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER {primary!r}. Expected one of: "
            f"{', '.join(sorted(_KNOWN_PROVIDERS))}."
        )

    fallbacks = [p.strip().lower() for p in settings.llm_fallbacks.split(",") if p.strip()]
    for name in fallbacks:
        if name not in _KNOWN_PROVIDERS:
            raise ValueError(
                f"Unknown provider {name!r} in LLM_FALLBACKS. Expected one of: "
                f"{', '.join(sorted(_KNOWN_PROVIDERS))}."
            )

    order = [primary]
    for name in fallbacks:
        if name not in order:
            order.append(name)
    return order


async def generate_with_fallback(
    *,
    system_prompt: str,
    user_content: str,
    settings: Settings | None = None,
) -> ProviderResult:
    settings = settings or get_settings()
    order = _resolve_provider_order(settings)

    for name in order:
        provider = _build_provider(name, settings)
        started = time.monotonic()
        try:
            text = await asyncio.wait_for(
                provider.generate(system_prompt=system_prompt, user_content=user_content),
                timeout=settings.llm_timeout_seconds,
            )
        except NoApiKeyConfiguredError:
            continue
        except ProviderUnavailableError as exc:
            logger.warning("LLM provider %r unavailable, trying next: %s", name, exc)
            continue
        except TimeoutError:
            # No provider is constructed with an SDK-level timeout (SDK
            # defaults run ~600s), and this call runs inside
            # run_scheduled_tick while holding the scheduler's advisory
            # lock — a hung provider must not stall every company's dispatch.
            logger.warning(
                "LLM provider %r timed out after %.0fs, trying next.",
                name,
                settings.llm_timeout_seconds,
            )
            continue
        if not text or not text.strip():
            # A safety-blocked or empty-candidate response (e.g. Gemini's
            # response.text is None, not an exception) is functionally the
            # same as the provider being unavailable — treat it the same way
            # rather than shipping it as a "successful" blank/crashing reply.
            logger.warning("LLM provider %r returned a blank response, trying next.", name)
            continue
        latency = time.monotonic() - started
        return ProviderResult(
            provider=name, model=provider.model, text=text, latency_seconds=latency
        )

    raise AllProvidersExhaustedError(
        f"All configured LLM providers failed or are unconfigured. Tried: {', '.join(order)}."
    )


async def extract_invoice_image_with_fallback(
    *,
    system_prompt: str,
    image_bytes: bytes,
    mime_type: str,
    settings: Settings | None = None,
) -> ProviderResult:
    """Same provider order/skip/abort semantics as generate_with_fallback, for
    the invoice-photo OCR path (app/services/invoice_ocr.py). A provider with
    supports_vision=False is skipped exactly like one with no API key — most
    of the configured chain (Groq/OpenRouter/GitHub Models/Cohere) has no
    multimodal path today, so this only ever actually calls Claude/Gemini.
    """
    settings = settings or get_settings()
    order = _resolve_provider_order(settings)

    for name in order:
        provider = _build_provider(name, settings)
        if not provider.supports_vision:
            continue
        started = time.monotonic()
        try:
            text = await asyncio.wait_for(
                provider.generate_from_image(
                    system_prompt=system_prompt, image_bytes=image_bytes, mime_type=mime_type
                ),
                timeout=settings.llm_timeout_seconds,
            )
        except (NoApiKeyConfiguredError, VisionUnsupportedError):
            continue
        except ProviderUnavailableError as exc:
            logger.warning("Vision provider %r unavailable, trying next: %s", name, exc)
            continue
        except TimeoutError:
            logger.warning(
                "Vision provider %r timed out after %.0fs, trying next.",
                name,
                settings.llm_timeout_seconds,
            )
            continue
        if not text or not text.strip():
            logger.warning("Vision provider %r returned a blank response, trying next.", name)
            continue
        latency = time.monotonic() - started
        return ProviderResult(
            provider=name, model=provider.model, text=text, latency_seconds=latency
        )

    raise AllProvidersExhaustedError(
        f"No configured vision-capable LLM provider succeeded. Tried: {', '.join(order)}."
    )


async def transcribe_audio_with_fallback(
    *,
    system_prompt: str,
    audio_bytes: bytes,
    mime_type: str,
    settings: Settings | None = None,
) -> ProviderResult:
    """Same provider order/skip/abort semantics as generate_with_fallback, for
    the voice-note transcription path (app/services/voice_transcription.py).
    A provider with supports_audio=False is skipped exactly like one with no
    API key — only Gemini implements audio input among the providers
    configured here, same restraint already applied to the vision-capable
    subset above.
    """
    settings = settings or get_settings()
    order = _resolve_provider_order(settings)

    for name in order:
        provider = _build_provider(name, settings)
        if not provider.supports_audio:
            continue
        started = time.monotonic()
        try:
            text = await asyncio.wait_for(
                provider.transcribe_audio(
                    system_prompt=system_prompt, audio_bytes=audio_bytes, mime_type=mime_type
                ),
                timeout=settings.llm_timeout_seconds,
            )
        except (NoApiKeyConfiguredError, AudioTranscriptionUnsupportedError):
            continue
        except ProviderUnavailableError as exc:
            logger.warning("Audio provider %r unavailable, trying next: %s", name, exc)
            continue
        except TimeoutError:
            logger.warning(
                "Audio provider %r timed out after %.0fs, trying next.",
                name,
                settings.llm_timeout_seconds,
            )
            continue
        if not text or not text.strip():
            logger.warning("Audio provider %r returned a blank response, trying next.", name)
            continue
        latency = time.monotonic() - started
        return ProviderResult(
            provider=name, model=provider.model, text=text, latency_seconds=latency
        )

    raise AllProvidersExhaustedError(
        f"No configured audio-capable LLM provider succeeded. Tried: {', '.join(order)}."
    )
