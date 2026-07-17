"""GitHubModelsProvider — GitHub Models' OpenAI-compatible chat completions
API via the `openai` SDK with a custom base_url, same shape as GroqProvider.

Free with just a GitHub account: the "API key" is actually a fine-grained
personal access token with the `models: read` permission — no separate
billing signup, no credit card, ever (unlike Cerebras, which markets a free
tier but still gates it behind a billing page). Rate-limited per model tier
rather than one shared account-wide quota, so it's an independent fallback
from every other provider here.
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

_BASE_URL = "https://models.github.ai/inference"


class GitHubModelsProvider(LLMProvider):
    def __init__(self, *, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self.model = model

    async def generate(self, *, system_prompt: str, user_content: str) -> str:
        if not self._api_key:
            raise NoApiKeyConfiguredError(
                "GITHUB_MODELS_API_KEY is not configured — set it in .env (a GitHub "
                "fine-grained personal access token with the 'models: read' permission) "
                "to use LLM_PROVIDER=github_models (or list it in LLM_FALLBACKS)."
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
            raise ProviderUnavailableError(f"GitHub Models rate limited: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(f"GitHub Models connection error: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailableError(f"GitHub Models server error: {exc}") from exc
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
            label="GitHub Models",
            system_prompt=system_prompt,
            messages=messages,
            tool_specs=tool_specs,
            execute=execute,
            max_steps=max_steps,
        )
