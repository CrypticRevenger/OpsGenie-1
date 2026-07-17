"""CohereProvider — Cohere's OpenAI-compatible Compatibility API via the
`openai` SDK with a custom base_url, same shape as GroqProvider.

Free trial keys are rate-limited to a monthly call cap (not a daily reset
like Groq/Gemini/OpenRouter), so it's an independent fallback that survives
a same-day exhaustion of every other provider's quota.
"""

from __future__ import annotations

from typing import Any

import openai

from app.services.llm._openai_tool_loop import run_openai_tool_loop
from app.services.llm.base import (
    ExecuteFn,
    LLMProvider,
    NoApiKeyConfiguredError,
    ProviderUnavailableError,
)

_BASE_URL = "https://api.cohere.ai/compatibility/v1"


class CohereProvider(LLMProvider):
    def __init__(self, *, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self.model = model

    async def generate(self, *, system_prompt: str, user_content: str) -> str:
        if not self._api_key:
            raise NoApiKeyConfiguredError(
                "COHERE_API_KEY is not configured — set it in .env to use "
                "LLM_PROVIDER=cohere (or list it in LLM_FALLBACKS)."
            )
        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=_BASE_URL)
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
        except openai.RateLimitError as exc:
            raise ProviderUnavailableError(f"Cohere rate limited: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(f"Cohere connection error: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailableError(f"Cohere server error: {exc}") from exc
            raise
        return response.choices[0].message.content

    async def run_tool_loop(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tool_specs: list[dict[str, Any]],
        execute: ExecuteFn,
        max_steps: int,
    ) -> str:
        return await run_openai_tool_loop(
            api_key=self._api_key,
            base_url=_BASE_URL,
            model=self.model,
            label="Cohere",
            system_prompt=system_prompt,
            messages=messages,
            tool_specs=tool_specs,
            execute=execute,
            max_steps=max_steps,
        )
