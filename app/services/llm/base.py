"""LLMProvider — the seam that makes SPEC.md's engineering principle literally
true in code, not just prose: "If you replace the LLM provider with any other
model tomorrow, every number and every recommendation must remain identical.
Only phrasing may change."

Every provider implementation receives an already-assembled system prompt and
user content — it has no access to the database, the snapshot, or the
recommendation engine. It cannot influence what numbers exist, only how they
are phrased. That boundary is enforced by this interface's shape, not just by
convention: `generate()` takes strings in, returns a string out.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

# execute(tool_name, args) -> JSON-safe dict. Runs a deterministic tool in our
# Python (never in the provider), so the DB boundary below still holds.
ExecuteFn = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class NoApiKeyConfiguredError(RuntimeError):
    """Raised by a provider's generate() when its own API key isn't set.
    The fallback orchestrator treats this as "skip silently" — not every
    provider needs to be configured at once.
    """


class ProviderUnavailableError(RuntimeError):
    """Raised by a provider's generate() for retryable failures only: rate
    limit, quota exhausted, 5xx, timeout/connection error. The fallback
    orchestrator catches this and moves to the next provider in the chain.

    Auth errors and bad-request errors must NOT be raised as this type —
    they should propagate as whatever exception the SDK raised, so the
    orchestrator aborts the whole chain immediately instead of masking a
    real credential or request problem behind an unrelated provider's retry.
    """


class AllProvidersExhaustedError(RuntimeError):
    """Raised by the fallback orchestrator when every provider in the
    resolved chain either has no key configured or failed retryably.
    """


class ToolCallingUnsupportedError(RuntimeError):
    """Raised by a provider whose model/SDK path doesn't do tool calling — the
    agent runner treats it like a missing key and skips to the next provider.
    """


@dataclass
class ProviderResult:
    """What a successful chain run returns — not just text, but which
    provider/model actually produced it and how long it took.
    """

    provider: str
    model: str
    text: str
    latency_seconds: float


class LLMProvider(ABC):
    """Narration-only interface. No provider implementation may read from or
    write to the database, or see anything beyond the two strings it's given.
    """

    model: str

    @abstractmethod
    async def generate(self, *, system_prompt: str, user_content: str) -> str:
        """Return the model's narrated text response."""
        raise NotImplementedError

    async def run_tool_loop(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tool_specs: list[dict[str, Any]],
        execute: ExecuteFn,
        max_steps: int,
    ) -> str:
        """Drive a tool-calling loop and return the final text.

        `messages` is the provider-agnostic dialogue so far
        (`[{"role": "user"|"assistant", "content": str}, …]`, current message
        last); `tool_specs` is `[{"name", "description", "parameters"}]`;
        `execute` runs a tool in our Python and returns a JSON-safe dict.
        Default: unsupported, so the runner skips this provider.
        """
        raise ToolCallingUnsupportedError(f"{type(self).__name__} does not support tool calling.")
