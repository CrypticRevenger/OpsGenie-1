"""generate_with_fallback() — the only public entry point external callers
(BriefingService) need. Resolves the provider order from config
(LLM_PROVIDER + LLM_FALLBACKS, no hardcoded canonical list), then tries each
in order: skip silently on missing key, log and move on for a retryable
failure, abort immediately on anything else (a real bug or bad credential
that another provider can't fix).
"""

from __future__ import annotations

import logging
import time

from app.core.config import Settings, get_settings
from app.services.llm.base import (
    AllProvidersExhaustedError,
    LLMProvider,
    NoApiKeyConfiguredError,
    ProviderResult,
    ProviderUnavailableError,
)
from app.services.llm.cerebras_provider import CerebrasProvider
from app.services.llm.claude_provider import ClaudeProvider
from app.services.llm.cohere_provider import CohereProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.github_models_provider import GitHubModelsProvider
from app.services.llm.groq_provider import GroqProvider
from app.services.llm.nvidia_provider import NvidiaProvider
from app.services.llm.openrouter_provider import OpenRouterProvider

logger = logging.getLogger(__name__)

_KNOWN_PROVIDERS = {
    "anthropic",
    "gemini",
    "groq",
    "openrouter",
    "cerebras",
    "github_models",
    "cohere",
    "nvidia",
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
    if name == "cerebras":
        return CerebrasProvider(api_key=settings.cerebras_api_key, model=settings.cerebras_model)
    if name == "github_models":
        return GitHubModelsProvider(
            api_key=settings.github_models_api_key, model=settings.github_models_model
        )
    if name == "cohere":
        return CohereProvider(api_key=settings.cohere_api_key, model=settings.cohere_model)
    if name == "nvidia":
        return NvidiaProvider(api_key=settings.nvidia_api_key, model=settings.nvidia_model)
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
            text = await provider.generate(system_prompt=system_prompt, user_content=user_content)
        except NoApiKeyConfiguredError:
            continue
        except ProviderUnavailableError as exc:
            logger.warning("LLM provider %r unavailable, trying next: %s", name, exc)
            continue
        latency = time.monotonic() - started
        return ProviderResult(
            provider=name, model=provider.model, text=text, latency_seconds=latency
        )

    raise AllProvidersExhaustedError(
        f"All configured LLM providers failed or are unconfigured. Tried: {', '.join(order)}."
    )
