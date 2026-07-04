"""ClaudeProvider — Anthropic implementation of LLMProvider.

SDK usage verified against the claude-api reference during this session:
`anthropic.AsyncAnthropic()`, `messages.create(model=..., max_tokens=...,
system=..., messages=[...])`, response text via `.content[i].text` blocks.
Typed exceptions (RateLimitError, APIConnectionError, APIStatusError) are
documented in that same reference's error-handling section.
"""

from __future__ import annotations

import anthropic

from app.services.llm.base import LLMProvider, NoApiKeyConfiguredError, ProviderUnavailableError


class ClaudeProvider(LLMProvider):
    def __init__(self, *, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self.model = model

    async def generate(self, *, system_prompt: str, user_content: str) -> str:
        if not self._api_key:
            raise NoApiKeyConfiguredError(
                "ANTHROPIC_API_KEY is not configured — set it in .env to use "
                "LLM_PROVIDER=anthropic (or list it in LLM_FALLBACKS)."
            )
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.RateLimitError as exc:
            raise ProviderUnavailableError(f"Claude rate limited: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailableError(f"Claude connection error: {exc}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailableError(f"Claude server error: {exc}") from exc
            raise  # 4xx other than rate limit — a real problem, don't fall back
        return "".join(block.text for block in response.content if block.type == "text")
