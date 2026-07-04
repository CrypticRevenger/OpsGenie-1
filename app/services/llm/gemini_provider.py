"""GeminiProvider — Google Gen AI implementation of LLMProvider.

Caveat: built from general knowledge of the `google-genai` package, not a
verified live reference (no equivalent skill was available for Gemini in this
session, unlike Claude) — including the exact exception hierarchy used below
for retryable-error classification. If the real SDK raises differently
shaped errors, this is the one file to fix — isolated behind the
LLMProvider interface, so a fix here touches nothing else in the codebase.
The broad `Exception` fallback below treats anything with a 429/5xx-looking
`status_code`/`code` attribute as retryable and re-raises everything else
unchanged, so a genuine auth/bad-request error still aborts the chain rather
than being silently retried against another provider.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from app.services.llm.base import LLMProvider, NoApiKeyConfiguredError, ProviderUnavailableError

_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class GeminiProvider(LLMProvider):
    def __init__(self, *, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self.model = model

    async def generate(self, *, system_prompt: str, user_content: str) -> str:
        if not self._api_key:
            raise NoApiKeyConfiguredError(
                "GEMINI_API_KEY is not configured — set it in .env to use "
                "LLM_PROVIDER=gemini (or list it in LLM_FALLBACKS)."
            )
        client = genai.Client(api_key=self._api_key)
        try:
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=user_content,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            )
        except Exception as exc:  # noqa: BLE001 - see module docstring
            status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if status_code in _RETRYABLE_STATUS_CODES:
                raise ProviderUnavailableError(f"Gemini unavailable: {exc}") from exc
            raise
        return response.text
