"""Locale registry for OpsGenie's multilingual support.

The DB column stays ``companies.preferred_language`` (compatibility — no
rename), but the value is always treated as a *locale* here: a language plus a
script/display style, resolved into a :class:`Locale` value object. Language
and script are kept as separate concepts so a new language or a Romanized
variant is one registry row + one catalog file, never a redesign.

Locale codes are BCP-47-ish: an ISO-639 language and an ISO-15924 script
subtag — ``en``, ``hi-Deva`` (Hindi, Devanagari), ``hi-Latn`` (Romanized
Hindi), ``or-Orya`` (Odia script), ``or-Latn`` (Romanized Odia).

Design note: most Indian WhatsApp users type their language in Latin letters
("Aji kete paisa milila?"), so the Romanized variants are first-class locales
and the *recommended default* for Hindi/Odia — not an afterthought or an
on-the-fly transliteration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Locale:
    code: str  # "hi-Latn"
    language: str  # "hi"  (ISO-639)
    script: str  # "Latn" | "Deva" | "Orya"  (ISO-15924)
    display_name: str  # "🇮🇳 Hindi (Romanized)" — shown in the language picker
    native_display: str  # a sample line, shown in onboarding's style step
    narration_instruction: str  # fed verbatim into the LLM system prompt


_LOCALES: dict[str, Locale] = {
    "en": Locale(
        code="en",
        language="en",
        script="Latn",
        display_name="🇬🇧 English",
        native_display="How much did I receive today?",
        narration_instruction="English",
    ),
    "hi-Deva": Locale(
        code="hi-Deva",
        language="hi",
        script="Deva",
        display_name="🇮🇳 Hindi (हिंदी)",
        native_display="आज कितने पैसे मिले?",
        narration_instruction="Hindi written in Devanagari script",
    ),
    "hi-Latn": Locale(
        code="hi-Latn",
        language="hi",
        script="Latn",
        display_name="🇮🇳 Hindi (Romanized)",
        native_display="Aaj kitne paise mile?",
        narration_instruction=(
            "Romanized Hindi — Hindi written in Latin/English letters as commonly "
            "typed on WhatsApp (e.g. 'Aaj kitne paise mile'), NOT Devanagari script"
        ),
    ),
    "or-Orya": Locale(
        code="or-Orya",
        language="or",
        script="Orya",
        display_name="🇮🇳 Odia (ଓଡ଼ିଆ)",
        native_display="ଆଜି କେତେ ଟଙ୍କା ମିଳିଲା?",
        narration_instruction="Odia written in the Odia (Oriya) script",
    ),
    "or-Latn": Locale(
        code="or-Latn",
        language="or",
        script="Latn",
        display_name="🇮🇳 Odia (Romanized)",
        native_display="Aji kete paisa milila?",
        narration_instruction=(
            "Romanized Odia — Odia written in Latin/English letters as commonly "
            "typed on WhatsApp (e.g. 'Aji kete paisa milila'), NOT the Odia script"
        ),
    ),
}

DEFAULT_LOCALE = _LOCALES["en"]
SUPPORTED_LOCALES: tuple[str, ...] = tuple(_LOCALES.keys())

# Native script per language, for onboarding's "Native" style option and for
# migrating a bare language name to a concrete locale.
_NATIVE_SCRIPT: dict[str, str] = {"hi": "Deva", "or": "Orya"}

# Bare language names / codes accepted by resolve_locale. A bare language
# (no script) resolves to its *Romanized* variant — the recommended default —
# matching the storage migration ("Hindi" -> hi-Latn).
_ALIASES: dict[str, str] = {
    "english": "en",
    "en": "en",
    "hindi": "hi-Latn",
    "hi": "hi-Latn",
    "odia": "or-Latn",
    "oriya": "or-Latn",
    "or": "or-Latn",
}


def get_locale(code: str) -> Locale | None:
    return _LOCALES.get(code)


def resolve_locale(raw: object) -> Locale:
    """Best-effort resolution to a supported :class:`Locale` — never raises.

    Accepts a ``Locale`` (passthrough), a ``Company`` (reads its
    ``preferred_language``), a canonical code (case-insensitive), or a bare
    language name/code. Anything unrecognized falls back to English, so a
    legacy or malformed stored value can never break a reply.
    """
    if isinstance(raw, Locale):
        return raw
    # Duck-typed Company (avoid importing the model here).
    stored = getattr(raw, "preferred_language", raw)
    if isinstance(stored, Locale):
        return stored
    if not stored:
        return DEFAULT_LOCALE
    key = str(stored).strip()
    for code, loc in _LOCALES.items():
        if key.lower() == code.lower():
            return loc
    alias = _ALIASES.get(key.lower())
    return _LOCALES[alias] if alias else DEFAULT_LOCALE


def compose_locale(language: str, *, romanized: bool) -> str:
    """Build a locale code from the two onboarding choices. English has no
    script variants; Hindi/Odia get Latn (Romanized) or their native script.
    """
    if language == "en":
        return "en"
    script = "Latn" if romanized else _NATIVE_SCRIPT[language]
    return f"{language}-{script}"
