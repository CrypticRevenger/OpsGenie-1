"""Generic command dispatch — Phase 8.

Not WhatsApp-specific: a registry of exact-match command strings to handlers,
so new commands (SPEC Step 13's follow-up flow, future menu options) extend
by registering a handler rather than by adding another branch to a growing
if/elif chain in the webhook.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RouterResult:
    notification_type: str
    reply: str


@dataclass(frozen=True)
class _CommandHandler(Generic[T]):
    notification_type: str
    build_reply: Callable[[T], str]


class CommandRouter(Generic[T]):
    """Exact-match command routing over some payload type T (e.g. Snapshot)."""

    def __init__(self) -> None:
        self._handlers: dict[str, _CommandHandler[T]] = {}

    def register(
        self, command: str, *, notification_type: str, build_reply: Callable[[T], str]
    ) -> None:
        self._handlers[command] = _CommandHandler(
            notification_type=notification_type, build_reply=build_reply
        )

    def match(self, text: str) -> str | None:
        """text.strip() must exactly equal a registered command; else None."""
        command = text.strip()
        return command if command in self._handlers else None

    def execute(self, command: str, payload: T) -> RouterResult:
        handler = self._handlers[command]
        return RouterResult(
            notification_type=handler.notification_type,
            reply=handler.build_reply(payload),
        )
