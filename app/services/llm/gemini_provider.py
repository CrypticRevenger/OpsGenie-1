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

from typing import Any

from google import genai
from google.genai import types

from app.services.llm.base import (
    ExecuteFn,
    LLMProvider,
    NoApiKeyConfiguredError,
    ProviderUnavailableError,
)

_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class GeminiProvider(LLMProvider):
    supports_vision = True
    supports_audio = True

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

    async def generate_from_image(
        self, *, system_prompt: str, image_bytes: bytes, mime_type: str
    ) -> str:
        if not self._api_key:
            raise NoApiKeyConfiguredError(
                "GEMINI_API_KEY is not configured — set it in .env to use "
                "LLM_PROVIDER=gemini (or list it in LLM_FALLBACKS)."
            )
        client = genai.Client(api_key=self._api_key)
        try:
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    system_prompt,
                ],
            )
        except Exception as exc:  # noqa: BLE001 - see module docstring
            status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if status_code in _RETRYABLE_STATUS_CODES:
                raise ProviderUnavailableError(f"Gemini unavailable: {exc}") from exc
            raise
        return response.text

    async def transcribe_audio(
        self, *, system_prompt: str, audio_bytes: bytes, mime_type: str
    ) -> str:
        if not self._api_key:
            raise NoApiKeyConfiguredError(
                "GEMINI_API_KEY is not configured — set it in .env to use "
                "LLM_PROVIDER=gemini (or list it in LLM_FALLBACKS)."
            )
        client = genai.Client(api_key=self._api_key)
        try:
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    system_prompt,
                ],
            )
        except Exception as exc:  # noqa: BLE001 - see module docstring
            status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if status_code in _RETRYABLE_STATUS_CODES:
                raise ProviderUnavailableError(f"Gemini unavailable: {exc}") from exc
            raise
        return response.text

    async def run_tool_loop(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tool_specs: list[dict[str, Any]],
        execute: ExecuteFn,
        max_steps: int,
    ) -> str:
        # Best-effort Gemini function calling. This is a middle fallback (the
        # OpenAI-compatible OpenRouter/Groq path is primary and covers two of
        # the three configured keys), so if the exact google-genai tool shapes
        # drift, the chain still works — same isolation caveat as the module
        # docstring above.
        if not self._api_key:
            raise NoApiKeyConfiguredError("GEMINI_API_KEY is not configured.")
        client = genai.Client(api_key=self._api_key)
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=t["name"], description=t["description"], parameters=t["parameters"]
                    )
                    for t in tool_specs
                ]
            )
        ]
        base_config = {"system_instruction": system_prompt}
        contents: list[types.Content] = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]

        async def _generate(*, with_tools: bool):
            config = types.GenerateContentConfig(**base_config, tools=tools if with_tools else None)
            try:
                return await client.aio.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            except Exception as exc:  # noqa: BLE001 - see module docstring
                status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if status_code in _RETRYABLE_STATUS_CODES:
                    raise ProviderUnavailableError(f"Gemini unavailable: {exc}") from exc
                raise

        # Gemini is a skippable middle fallback, so ANY failure here — a network
        # error, a 400 for an odd content/role order, a safety-blocked response
        # with empty candidates (IndexError), or `.text` raising on a non-text
        # finish — must skip to the next provider, never abort the whole chain.
        # So every non-ProviderUnavailable exception is converted to one.
        try:
            for _ in range(max_steps):
                response = await _generate(with_tools=True)
                calls = response.function_calls
                if not calls:
                    return response.text
                contents.append(response.candidates[0].content)
                response_parts = [
                    types.Part.from_function_response(
                        name=fc.name, response=await execute(fc.name, dict(fc.args or {}))
                    )
                    for fc in calls
                ]
                contents.append(types.Content(role="user", parts=response_parts))

            final = await _generate(with_tools=False)
            return final.text
        except ProviderUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - skip, don't kill the chain (see above)
            raise ProviderUnavailableError(f"Gemini tool loop failed: {exc}") from exc
