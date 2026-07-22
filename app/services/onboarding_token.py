"""Short-lived signed capability token for the public self-serve onboarding routes.

Why this exists
---------------
`POST /onboard` is unauthenticated by necessity — a distributor signing up has
no credential yet. It used to return `company_id` on *both* the "registered"
and "already_registered" branches, which made it an oracle: a WhatsApp number
is public (it is printed on invoices and encoded in the wa.me link), so anyone
could post a victim's number, receive that company's real UUID, and then use it
against the two routes that accept a bare UUID —
`POST /onboard/{id}/import` (writes dealers/suppliers/invoices into their
books, and returns their real receivable/payable totals in the response) and
`POST /onboard/{id}/activate`.

Both routes guarded themselves with a state gate whose own docstring says it
exists so "any leaked/guessed UUID" can't be used. The register endpoint was
handing that UUID out, which defeated it.

The fix is a bearer token issued only to the caller that actually created the
registration, and required by both routes afterwards. `already_registered`
now returns no id and no token at all, so knowing a phone number reveals
nothing.

Design
------
Stateless HMAC over `company_id:expires_at`, exactly like
`company_export.py`'s signed export links — nothing to store, nothing to
revoke, and no migration. Two deliberate differences from that module:

- **Domain separation.** The signed message is prefixed with `onboarding:`,
  so an export-link signature can never be replayed as an onboarding token
  (or vice versa) even though they may share a secret.
- **Its own secret, with a fallback.** `ONBOARDING_TOKEN_SECRET` allows
  rotating this independently later; unset, it falls back to
  `EXPORT_LINK_SECRET`, which is already configured wherever export links
  work. That keeps this deployable without a new production env var while
  still failing closed when neither is set.

The TTL is deliberately generous (hours, not the export link's minutes): a
distributor may leave the wizard open while they hunt for their Tally export
before reaching the upload step.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from app.core.config import get_settings

_DOMAIN = "onboarding"
TOKEN_TTL_SECONDS = 6 * 60 * 60


def _secret() -> str | None:
    settings = get_settings()
    return settings.onboarding_token_secret or settings.export_link_secret


def _sign(company_id: uuid.UUID, expires_at: int, secret: str) -> str:
    message = f"{_DOMAIN}:{company_id}:{expires_at}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def generate_onboarding_token(company_id: uuid.UUID) -> str:
    """Issue a token for a freshly registered company.

    Raises ValueError when no secret is configured — fail closed rather than
    mint an unverifiable token that would then be accepted by nothing.
    """
    secret = _secret()
    if not secret:
        raise ValueError(
            "Neither ONBOARDING_TOKEN_SECRET nor EXPORT_LINK_SECRET is configured; "
            "cannot issue an onboarding token."
        )
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    return f"{expires_at}.{_sign(company_id, expires_at, secret)}"


def verify_onboarding_token(company_id: uuid.UUID, token: str | None) -> bool:
    """True only for a live, untampered token issued for *this* company."""
    secret = _secret()
    if not secret or not token:
        return False
    expires_at_raw, _, signature = token.partition(".")
    if not signature:
        return False
    try:
        expires_at = int(expires_at_raw)
    except ValueError:
        return False
    if time.time() > expires_at:
        return False
    return hmac.compare_digest(_sign(company_id, expires_at, secret), signature)
