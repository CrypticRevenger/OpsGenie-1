"""Agent runner — drives the tool-calling loop across the provider fallback chain.

Reuses the LLM factory's config-driven chain resolution (`LLM_PROVIDER` +
`LLM_FALLBACKS`), but instead of a single text generation it calls each
provider's `run_tool_loop`. A provider with no key, no tool-calling support, or
a retryable failure is skipped to the next — same taxonomy as text generation.
Tool *execution* happens in `ToolContext.execute` (our Python); the runner only
records which provider answered and the tool outputs (for the money gate).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.services.agent.base import ToolContext
from app.services.llm.base import (
    AllProvidersExhaustedError,
    NoApiKeyConfiguredError,
    ProviderUnavailableError,
    ToolCallingUnsupportedError,
)
from app.services.llm.factory import _build_provider, _resolve_provider_order

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    text: str
    tool_outputs: list[dict[str, Any]]
    provider: str
    model: str


async def run_agent(
    *,
    system_prompt: str,
    messages: list[dict[str, Any]],
    ctx: ToolContext,
    settings: Settings | None = None,
) -> AgentResult:
    """Run the agent over `messages` (dialogue so far, current turn last) with
    the tools bound in `ctx`. Raises AllProvidersExhaustedError if no configured
    provider can serve a tool-calling request.
    """
    settings = settings or get_settings()
    order = _resolve_provider_order(settings)
    tool_specs = [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in ctx.tools.values()
    ]

    for name in order:
        provider = _build_provider(name, settings)
        try:
            text = await provider.run_tool_loop(
                system_prompt=system_prompt,
                messages=messages,
                tool_specs=tool_specs,
                execute=ctx.execute,
                max_steps=settings.agent_max_steps,
            )
        except NoApiKeyConfiguredError:
            continue
        except ToolCallingUnsupportedError:
            logger.info("Provider %r has no tool-calling support, trying next.", name)
            continue
        except ProviderUnavailableError as exc:
            logger.warning("Agent provider %r unavailable, trying next: %s", name, exc)
            continue
        except Exception as exc:  # noqa: BLE001 - resilience: any provider error → try the next
            # A free-tier model can return a non-retryable quirk (a 400 on a
            # malformed tool call, an odd response shape). For the agent we'd
            # rather fall through to the next provider than abort to a fallback,
            # so every provider failure is skippable here (the final
            # AllProvidersExhausted is what surfaces to the never-raise caller).
            logger.warning("Agent provider %r errored, trying next: %s", name, exc)
            continue
        return AgentResult(
            text=text or "", tool_outputs=ctx.outputs, provider=name, model=provider.model
        )

    raise AllProvidersExhaustedError(
        f"No configured provider could run the agent. Tried: {', '.join(order)}."
    )
