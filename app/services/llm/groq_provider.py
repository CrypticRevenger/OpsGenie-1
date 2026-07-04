"""GroqProvider — Groq's OpenAI-compatible chat completions API via the
`openai` SDK with a custom base_url. No dedicated Groq SDK needed.
"""

from __future__ import annotations

import openai

from app.services.llm.base import LLMProvider, NoApiKeyConfiguredError, ProviderUnavailableError

_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(LLMProvider):
    def __init__(self, *, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self.model = model

    async def generate(self, *, system_prompt: str, user_content: str) -> str:
        if not self._api_key:
            raise NoApiKeyConfiguredError(
                "GROQ_API_KEY is not configured — set it in .env to use "
                "LLM_PROVIDER=groq (or list it in LLM_FALLBACKS)."
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
            raise ProviderUnavailableError(f"Groq rate limited: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(f"Groq connection error: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailableError(f"Groq server error: {exc}") from exc
            raise
        return response.choices[0].message.content
