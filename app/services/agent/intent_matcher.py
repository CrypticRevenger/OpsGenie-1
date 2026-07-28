"""Local, deterministic fuzzy matching over a fixed set of read-only instant-
report command phrases.

Sits between the webhook's exact-match dispatch and the LLM assistant (see
app/api/webhooks/whatsapp.py's _handle_text_message) so a paraphrase like
"provide me the stock I have" resolves without depending on a free-tier LLM's
tool-calling reliability or the money-safety guard rejecting an ungrounded
aggregate figure (see app/services/agent/money_guard.py) — both real failure
modes the exact reply ladder already warns about.

Deliberately local and synchronous: RapidFuzz's token_set_ratio over a few
dozen short canonical phrases needs no network call, no API key, and no
timeout handling. A miss just returns None and the caller falls through to
the LLM exactly as before — this only ever adds coverage, never a regression
path. Embeddings (semantic matching beyond lexical overlap) are a possible
future stage if real production misses show fuzzy matching genuinely can't
reach them — not built here.

Only ever constructed over a caller-supplied allowlist, never a full command
dict — see whatsapp.py's own exclusion list for why: state-changing phrases
(undo/void payment or order, opt-in-all-dealers, enable/disable dealer
self-service, change language) must stay exact-match-only, so a near-miss
fuzzy score can never nudge someone toward an unintended action.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache

from rapidfuzz import fuzz, process
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.company import Company

InstantHandler = Callable[[AsyncSession, Company], Awaitable[str]]


class FuzzyCommandMatcher:
    """Wraps a fixed {phrase: handler} dict with cached RapidFuzz lookup.

    enabled/threshold are read fresh from settings on every match() call
    (not baked in at construction) so the INSTANT_FUZZY_MATCH_ENABLED kill
    switch takes effect without rebuilding the matcher. The RapidFuzz scoring
    itself is cached per normalized input text (a small in-process LRU) since
    the phrase list is static — a repeated identical free-text query (common
    on WhatsApp) skips re-scoring against every canonical phrase.
    """

    def __init__(self, commands: dict[str, InstantHandler]) -> None:
        self._commands = commands
        self._phrases = list(commands.keys())
        self._best_match = lru_cache(maxsize=512)(self._best_match_uncached)

    def _best_match_uncached(self, normalized: str) -> tuple[str, float] | None:
        if not normalized or not self._phrases:
            return None
        result = process.extractOne(normalized, self._phrases, scorer=fuzz.token_set_ratio)
        if result is None:
            return None
        phrase, score, _index = result
        return phrase, score

    def match(self, text: str) -> InstantHandler | None:
        settings = get_settings()
        if not settings.instant_fuzzy_match_enabled:
            return None
        best = self._best_match(text.strip().lower())
        if best is None:
            return None
        phrase, score = best
        if score < settings.instant_fuzzy_threshold:
            return None
        return self._commands[phrase]
