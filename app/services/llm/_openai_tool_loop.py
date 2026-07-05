"""Shared OpenAI-compatible tool-calling loop for Groq and OpenRouter.

Both providers speak the OpenAI chat-completions API (only base_url/key/model
differ), so the multi-step tool loop lives here once. The tools are *executed*
by the caller's `execute` callback in our Python — the provider only relays the
model's tool-call requests and the results — so `llm/base.py`'s "provider never
touches the DB" boundary is preserved.
"""

from __future__ import annotations

import json
from typing import Any

import openai

from app.services.llm.base import (
    ExecuteFn,
    NoApiKeyConfiguredError,
    ProviderUnavailableError,
)


def _to_openai_tools(tool_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tool_specs
    ]


async def run_openai_tool_loop(
    *,
    api_key: str | None,
    base_url: str,
    model: str,
    label: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tool_specs: list[dict[str, Any]],
    execute: ExecuteFn,
    max_steps: int,
) -> str:
    if not api_key:
        raise NoApiKeyConfiguredError(f"{label} API key is not configured.")

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    convo: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *messages]
    tools = _to_openai_tools(tool_specs)

    async def _create(*, with_tools: bool):
        kwargs: dict[str, Any] = {"model": model, "messages": convo}
        if with_tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            return await client.chat.completions.create(**kwargs)
        except openai.RateLimitError as exc:
            raise ProviderUnavailableError(f"{label} rate limited: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(f"{label} connection error: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailableError(f"{label} server error: {exc}") from exc
            raise

    for _ in range(max_steps):
        response = await _create(with_tools=True)
        message = response.choices[0].message
        if not message.tool_calls:
            return message.content or ""

        convo.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in message.tool_calls
                ],
            }
        )
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await execute(tc.function.name, args)
            convo.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

    # Step budget spent — ask once more with no tools so the model must answer
    # in text rather than request yet another call.
    final = await _create(with_tools=False)
    return final.choices[0].message.content or ""
