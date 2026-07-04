"""CommandRouter unit tests — Phase 8.

Pure in-memory tests, no DB — the routing mechanism (register/match/execute)
is generic over any payload type, so it's tested here with a plain str
payload rather than a real Snapshot.
"""

from __future__ import annotations

import pytest
from app.services.command_router import CommandRouter, RouterResult


def _router() -> CommandRouter[str]:
    router: CommandRouter[str] = CommandRouter()
    router.register("1", notification_type="one", build_reply=lambda payload: f"one:{payload}")
    router.register("2", notification_type="two", build_reply=lambda payload: f"two:{payload}")
    return router


def test_match_exact_command():
    router = _router()
    assert router.match("1") == "1"
    assert router.match("2") == "2"


def test_match_strips_whitespace():
    router = _router()
    assert router.match("  1  ") == "1"


def test_match_unknown_command_returns_none():
    router = _router()
    assert router.match("9") is None
    assert router.match("hello") is None
    assert router.match("") is None


def test_execute_dispatches_to_registered_handler():
    router = _router()
    result = router.execute("1", "payload-value")
    assert isinstance(result, RouterResult)
    assert result.notification_type == "one"
    assert result.reply == "one:payload-value"


def test_execute_unknown_command_raises_keyerror():
    router = _router()
    with pytest.raises(KeyError):
        router.execute("9", "payload-value")


def test_register_overwrites_existing_command():
    router = _router()
    router.register("1", notification_type="replaced", build_reply=lambda payload: "new-reply")
    result = router.execute("1", "ignored")
    assert result.notification_type == "replaced"
    assert result.reply == "new-reply"
