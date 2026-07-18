"""OpsGenie internationalization.

`t(key, locale, **params)` is the single entry point every deterministic
surface uses to produce a user-facing string in the company's chosen locale.
The LLM narration path is language-aware separately (it reads
`Locale.narration_instruction`); this module covers the deterministic text
(menu, reports, workflows, onboarding, notifications, confirmations, errors).

English is always the source of truth and the fallback: a key missing from a
non-English catalog degrades to the English string rather than failing, so a
partial translation can never break a reply.
"""

from __future__ import annotations

import logging

from app.i18n.catalog import CATALOGS
from app.i18n.languages import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    Locale,
    compose_locale,
    get_locale,
    resolve_locale,
)

__all__ = [
    "CATALOGS",
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "Locale",
    "compose_locale",
    "get_locale",
    "resolve_locale",
    "t",
]

logger = logging.getLogger(__name__)


def t(key: str, locale: Locale | str | object, /, **params: object) -> str:
    """Render catalog message ``key`` in ``locale``, interpolating ``params``.

    ``locale`` may be a Locale, a locale code, or a Company (resolved via
    resolve_locale). Lookup order: the locale's own catalog → English →
    (last resort) the key itself. Bad/missing interpolation never raises — it
    logs and returns the best available text — so this stays safe to call from
    the webhook path.
    """
    loc = locale if isinstance(locale, Locale) else resolve_locale(locale)

    template = CATALOGS.get(loc.code, {}).get(key)
    if template is None:
        template = CATALOGS["en"].get(key)
        if template is None:
            # A key missing from English is a programming error — tests/test_i18n.py
            # guarantees this never happens; in prod we log and degrade to the key
            # rather than raising into a live WhatsApp reply.
            logger.error("i18n: missing English catalog key %r", key)
            return key

    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError) as exc:
        logger.error("i18n: bad interpolation for key %r locale %r: %s", key, loc.code, exc)
        en_template = CATALOGS["en"].get(key, key)
        try:
            return en_template.format(**params)
        except (KeyError, IndexError, ValueError):
            return en_template
