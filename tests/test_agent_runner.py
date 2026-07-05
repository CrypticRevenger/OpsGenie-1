"""Agent runner + OpenAI tool-loop tests (no network).

The runner is tested with a fake provider; the shared OpenAI tool loop is tested
with a fake OpenAI client so the multi-step + max-steps behaviour is exercised
without real API calls.

    uv run pytest tests/test_agent_runner.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.services.agent import runner as runner_mod
from app.services.agent.base import ToolContext
from app.services.agent.runner import run_agent
from app.services.llm.base import (
    AllProvidersExhaustedError,
    ProviderUnavailableError,
    ToolCallingUnsupportedError,
)


class _FakeProvider:
    def __init__(self, behavior):
        self.model = "fake-model"
        self._behavior = behavior

    async def run_tool_loop(self, *, system_prompt, messages, tool_specs, execute, max_steps):
        return await self._behavior(execute)


def _patch_chain(monkeypatch, providers: dict):
    monkeypatch.setattr(runner_mod, "_resolve_provider_order", lambda s: list(providers.keys()))
    monkeypatch.setattr(runner_mod, "_build_provider", lambda name, s: providers[name])


def _ctx() -> ToolContext:
    # A tiny tool registry that records a known output when called.
    async def _echo(db, company, **args):
        return {"outstanding": "42000.00"}

    tool = SimpleNamespace(name="get_party_balance", description="d", parameters={}, executor=_echo)
    return ToolContext(db=None, company=SimpleNamespace(id="c1"), tools={"get_party_balance": tool})


@pytest.mark.asyncio
async def test_business_question_drives_tool_call(monkeypatch) -> None:
    async def _behave(execute):
        out = await execute("get_party_balance", {"name": "Ram"})
        return f"Ram owes you ₹{out['outstanding']}."

    _patch_chain(monkeypatch, {"openrouter": _FakeProvider(_behave)})
    ctx = _ctx()
    result = await run_agent(
        system_prompt="s", messages=[{"role": "user", "content": "ram?"}], ctx=ctx
    )
    assert "42000.00" in result.text
    assert result.tool_outputs == [{"outstanding": "42000.00"}]  # recorded for the gate
    assert result.provider == "openrouter"


@pytest.mark.asyncio
async def test_greeting_no_tool_call(monkeypatch) -> None:
    async def _behave(execute):
        return "Hi! How can I help with your business today?"

    _patch_chain(monkeypatch, {"openrouter": _FakeProvider(_behave)})
    ctx = _ctx()
    result = await run_agent(
        system_prompt="s", messages=[{"role": "user", "content": "hi"}], ctx=ctx
    )
    assert "Hi!" in result.text
    assert result.tool_outputs == []  # no tool used for chitchat


@pytest.mark.asyncio
async def test_skips_unsupported_and_unavailable_to_next(monkeypatch) -> None:
    async def _boom_unsupported(execute):
        raise ToolCallingUnsupportedError("no tools")

    async def _boom_unavailable(execute):
        raise ProviderUnavailableError("rate limited")

    async def _ok(execute):
        return "answered"

    _patch_chain(
        monkeypatch,
        {
            "openrouter": _FakeProvider(_boom_unsupported),
            "gemini": _FakeProvider(_boom_unavailable),
            "groq": _FakeProvider(_ok),
        },
    )
    result = await run_agent(
        system_prompt="s", messages=[{"role": "user", "content": "x"}], ctx=_ctx()
    )
    assert result.text == "answered"
    assert result.provider == "groq"


@pytest.mark.asyncio
async def test_all_exhausted_raises(monkeypatch) -> None:
    async def _boom(execute):
        raise ProviderUnavailableError("down")

    _patch_chain(monkeypatch, {"openrouter": _FakeProvider(_boom)})
    with pytest.raises(AllProvidersExhaustedError):
        await run_agent(system_prompt="s", messages=[{"role": "user", "content": "x"}], ctx=_ctx())


# ── Shared OpenAI tool loop: multi-step + max-steps guard ─────────────────────


@pytest.mark.asyncio
async def test_openai_loop_stops_at_max_steps(monkeypatch) -> None:
    """A model that keeps requesting tools must be capped, then answer text-only."""
    import app.services.llm._openai_tool_loop as loop_mod

    calls = {"with_tools": 0, "without_tools": 0}

    def _tool_call_msg():
        fn = SimpleNamespace(name="get_x", arguments="{}")
        tc = SimpleNamespace(id="call_1", function=fn)
        return SimpleNamespace(content=None, tool_calls=[tc])

    def _final_msg():
        return SimpleNamespace(content="final answer", tool_calls=None)

    class _FakeCompletions:
        async def create(self, **kwargs):
            if "tools" in kwargs:
                calls["with_tools"] += 1
                return SimpleNamespace(choices=[SimpleNamespace(message=_tool_call_msg())])
            calls["without_tools"] += 1
            return SimpleNamespace(choices=[SimpleNamespace(message=_final_msg())])

    class _FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(loop_mod.openai, "AsyncOpenAI", _FakeClient)

    async def _execute(name, args):
        return {"value": "1"}

    text = await loop_mod.run_openai_tool_loop(
        api_key="k",
        base_url="http://x",
        model="m",
        label="Fake",
        system_prompt="s",
        messages=[{"role": "user", "content": "loop forever"}],
        tool_specs=[{"name": "get_x", "description": "d", "parameters": {}}],
        execute=_execute,
        max_steps=3,
    )
    assert text == "final answer"
    assert calls["with_tools"] == 3  # exactly the step budget
    assert calls["without_tools"] == 1  # one final tool-less call to force text


@pytest.mark.asyncio
async def test_openai_loop_returns_direct_answer(monkeypatch) -> None:
    import app.services.llm._openai_tool_loop as loop_mod

    class _FakeCompletions:
        async def create(self, **kwargs):
            msg = SimpleNamespace(content="just chatting", tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    class _FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(loop_mod.openai, "AsyncOpenAI", _FakeClient)

    async def _execute(name, args):
        return {}

    text = await loop_mod.run_openai_tool_loop(
        api_key="k",
        base_url="http://x",
        model="m",
        label="Fake",
        system_prompt="s",
        messages=[{"role": "user", "content": "hi"}],
        tool_specs=[],
        execute=_execute,
        max_steps=5,
    )
    assert text == "just chatting"
