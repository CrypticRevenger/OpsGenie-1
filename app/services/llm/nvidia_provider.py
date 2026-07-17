"""NvidiaProvider — NVIDIA NIM's (build.nvidia.com) OpenAI-compatible API
via the `openai` SDK with a custom base_url, same shape as GroqProvider.

Less independently verified than the other providers here (web search was
unavailable while wiring this up — see the .env comment) — confirm the
default model is actually usable on your account before relying on it, the
same way Cerebras' default model turned out to need a paid plan.
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

_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaProvider(LLMProvider):
    def __init__(self, *, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self.model = model

    async def generate(self, *, system_prompt: str, user_content: str) -> str:
        if not self._api_key:
            raise NoApiKeyConfiguredError(
                "NVIDIA_API_KEY is not configured — set it in .env to use "
                "LLM_PROVIDER=nvidia (or list it in LLM_FALLBACKS)."
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
            raise ProviderUnavailableError(f"NVIDIA rate limited: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(f"NVIDIA connection error: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailableError(f"NVIDIA server error: {exc}") from exc
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
            label="NVIDIA",
            system_prompt=system_prompt,
            messages=messages,
            tool_specs=tool_specs,
            execute=execute,
            max_steps=max_steps,
        )
