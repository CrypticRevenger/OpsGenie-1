"""i18n framework guardrails.

The catalogs are hand-maintained across 5 locales, so these tests are what
keep them honest: every locale must define the exact same keys as English,
and every key's ``{placeholder}`` set must match English so ``t()`` can never
raise a KeyError on interpolation in production. Also covers locale resolution
and the English fallback.
"""

from __future__ import annotations

import string
from types import SimpleNamespace

import pytest
from app.i18n import CATALOGS, SUPPORTED_LOCALES, compose_locale, resolve_locale, t
from app.i18n.languages import DEFAULT_LOCALE, Locale, get_locale


def _placeholders(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name
    }


def test_every_supported_locale_has_a_catalog() -> None:
    for code in SUPPORTED_LOCALES:
        assert code in CATALOGS, f"no catalog registered for locale {code}"


@pytest.mark.parametrize("code", [c for c in SUPPORTED_LOCALES if c != "en"])
def test_catalog_keys_match_english(code: str) -> None:
    en_keys = set(CATALOGS["en"])
    other_keys = set(CATALOGS[code])
    missing = en_keys - other_keys
    extra = other_keys - en_keys
    assert not missing, f"{code} is missing keys present in English: {sorted(missing)}"
    assert not extra, f"{code} has keys not in English: {sorted(extra)}"


@pytest.mark.parametrize("code", [c for c in SUPPORTED_LOCALES if c != "en"])
def test_placeholders_match_english_per_key(code: str) -> None:
    for key, en_template in CATALOGS["en"].items():
        if key not in CATALOGS[code]:
            continue  # covered by the key-parity test above
        assert _placeholders(en_template) == _placeholders(CATALOGS[code][key]), (
            f"placeholder mismatch for key {key!r} in locale {code}"
        )


def test_resolve_locale_canonical_codes() -> None:
    for code in SUPPORTED_LOCALES:
        assert resolve_locale(code).code == code


def test_resolve_locale_is_case_insensitive() -> None:
    assert resolve_locale("HI-LATN").code == "hi-Latn"


def test_resolve_locale_bare_language_defaults_to_romanized() -> None:
    # A bare language name resolves to its Romanized variant (the recommended
    # default) — matches the storage migration's Hindi -> hi-Latn.
    assert resolve_locale("Hindi").code == "hi-Latn"
    assert resolve_locale("odia").code == "or-Latn"
    assert resolve_locale("oriya").code == "or-Latn"
    assert resolve_locale("English").code == "en"


def test_resolve_locale_unknown_and_empty_fall_back_to_english() -> None:
    assert resolve_locale("klingon").code == "en"
    assert resolve_locale("").code == "en"
    assert resolve_locale(None).code == "en"


def test_resolve_locale_accepts_company_like_object() -> None:
    company = SimpleNamespace(preferred_language="or-Latn")
    assert resolve_locale(company).code == "or-Latn"


def test_resolve_locale_passthrough_locale() -> None:
    loc = get_locale("hi-Deva")
    assert isinstance(loc, Locale)
    assert resolve_locale(loc) is loc


def test_compose_locale() -> None:
    assert compose_locale("en", romanized=True) == "en"
    assert compose_locale("hi", romanized=True) == "hi-Latn"
    assert compose_locale("hi", romanized=False) == "hi-Deva"
    assert compose_locale("or", romanized=True) == "or-Latn"
    assert compose_locale("or", romanized=False) == "or-Orya"


def test_t_renders_localized_string() -> None:
    en = t("errors.something_wrong", "en")
    hi = t("errors.something_wrong", "hi-Latn")
    assert en and hi and en != hi


def test_t_accepts_locale_object_and_code() -> None:
    loc = get_locale("or-Latn")
    assert t("errors.something_wrong", loc) == t("errors.something_wrong", "or-Latn")


def test_t_falls_back_to_english_for_missing_non_english_key(monkeypatch) -> None:
    # A key present only in English must render the English text for any locale,
    # never crash — this is the guarantee that a partial translation is safe.
    monkeypatch.setitem(CATALOGS["en"], "test.only_en", "English only {x}")
    assert t("test.only_en", "hi-Latn", x=5) == "English only 5"


def test_t_missing_everywhere_returns_key() -> None:
    assert t("no.such.key.anywhere", "en") == "no.such.key.anywhere"


def test_every_locale_has_a_narration_instruction() -> None:
    for code in SUPPORTED_LOCALES:
        loc = get_locale(code)
        assert loc is not None
        assert loc.narration_instruction.strip()
        assert loc.display_name.strip()
        assert loc.native_display.strip()


def test_default_locale_is_english() -> None:
    assert DEFAULT_LOCALE.code == "en"
