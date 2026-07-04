"""Pluggable LLM narration providers with automatic failover — see base.py for
the interface contract and factory.py for the chain orchestrator.
"""

from __future__ import annotations

from app.services.llm.base import (
    AllProvidersExhaustedError,
    LLMProvider,
    NoApiKeyConfiguredError,
    ProviderResult,
    ProviderUnavailableError,
)
from app.services.llm.claude_provider import ClaudeProvider
from app.services.llm.factory import generate_with_fallback
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.groq_provider import GroqProvider
from app.services.llm.openrouter_provider import OpenRouterProvider

__all__ = [
    "AllProvidersExhaustedError",
    "ClaudeProvider",
    "GeminiProvider",
    "GroqProvider",
    "LLMProvider",
    "NoApiKeyConfiguredError",
    "OpenRouterProvider",
    "ProviderResult",
    "ProviderUnavailableError",
    "generate_with_fallback",
]
