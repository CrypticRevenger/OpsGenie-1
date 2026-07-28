"""FuzzyCommandMatcher — local RapidFuzz matching over read-only instant-
report phrases. No network, no DB: pure scoring logic, plus a couple of
checks against the real, wired-up matcher built in app.api.webhooks.whatsapp
(confirming the read-only exclusion filter actually applies there, not just
in a toy example).
"""

from __future__ import annotations

from app.core.config import get_settings
from app.services.agent.intent_matcher import FuzzyCommandMatcher


async def _stub_handler(db, company) -> str:  # noqa: ANN001 - test stand-in, never called
    return "stub"


async def _other_handler(db, company) -> str:  # noqa: ANN001 - test stand-in, never called
    return "other"


def _toy_matcher() -> FuzzyCommandMatcher:
    return FuzzyCommandMatcher(
        {
            "inventory": _stub_handler,
            "stock": _stub_handler,
            "recent inventory": _stub_handler,
            "products": _stub_handler,
            "cash position": _other_handler,
            "cash": _other_handler,
        }
    )


def test_close_paraphrase_matches_expected_handler():
    matcher = _toy_matcher()
    assert matcher.match("provide me the stock I have") is _stub_handler
    assert matcher.match("show me what is in stock") is _stub_handler
    assert matcher.match("what products do i have") is _stub_handler


def test_exact_phrase_still_matches():
    matcher = _toy_matcher()
    assert matcher.match("stock") is _stub_handler
    assert matcher.match("Cash Position") is _other_handler


def test_unrelated_message_returns_none():
    matcher = _toy_matcher()
    assert matcher.match("hows the weather today") is None


def test_disabled_via_settings_returns_none(monkeypatch):
    matcher = _toy_matcher()
    monkeypatch.setattr(get_settings(), "instant_fuzzy_match_enabled", False)
    assert matcher.match("provide me the stock I have") is None


def test_threshold_gates_low_confidence_matches(monkeypatch):
    matcher = _toy_matcher()
    # A borderline (misspelled) match that clears the default threshold...
    assert matcher.match("stok") is _stub_handler
    # ...but not an unreasonably high one.
    monkeypatch.setattr(get_settings(), "instant_fuzzy_threshold", 95.0)
    assert matcher.match("stok") is None


def test_empty_and_whitespace_input_returns_none():
    matcher = _toy_matcher()
    assert matcher.match("") is None
    assert matcher.match("   ") is None


def test_repeated_identical_query_uses_cache_consistently():
    matcher = _toy_matcher()
    first = matcher.match("provide me the stock I have")
    second = matcher.match("provide me the stock I have")
    assert first is second is _stub_handler


# ── Against the real, wired-up matcher (app.api.webhooks.whatsapp) ─────────
# Confirms the actual production allowlist — not just a toy dict — both
# resolves the originally reported bug and keeps write-triggering phrases
# exact-match-only.


def test_reported_bug_case_resolves_via_real_matcher():
    from app.api.webhooks import whatsapp

    handler = whatsapp._fuzzy_matcher.match("Provide me the stock I have")
    assert handler is not None
    assert handler.__name__ == "recent_inventory_reply"


def test_write_triggering_phrase_excluded_from_real_matcher():
    from app.api.webhooks import whatsapp

    # Close in wording to the exact-match "undo last payment"/"void order"/
    # "opt in all dealers" trigger phrases. The real invariant: whatever
    # comes back — including a different, legitimate read-only report that
    # happens to score higher (e.g. "opt in all my dealers please" scoring
    # closer to the read-only "all dealers" than to the excluded opt-in
    # handler) — must never be one of the write-triggering handlers filtered
    # out of the allowlist. It must never be the excluded handler itself,
    # regardless of how high that phrase would otherwise score.
    close_paraphrases = [
        "please undo my last payment",
        "void that last order please",
        "i want to change my language",
        "opt in all my dealers please",
        "enable self service for my dealers",
        "disable dealer self service please",
    ]
    for phrase in close_paraphrases:
        handler = whatsapp._fuzzy_matcher.match(phrase)
        assert handler not in whatsapp._FUZZY_MATCH_EXCLUDED_HANDLERS, phrase

    # And the two clearest cases genuinely return no match at all (score too
    # low against anything in the allowlist).
    assert whatsapp._fuzzy_matcher.match("please undo my last payment") is None
    assert whatsapp._fuzzy_matcher.match("void that last order please") is None
