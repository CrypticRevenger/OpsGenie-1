"""WhatsApp outbound sending — Phase 8.

Fail-closed, same convention as admin_api_key / whatsapp_app_secret / each
LLMProvider's NoApiKeyConfiguredError: an unconfigured token/phone number ID
raises rather than silently no-op-ing. Callers (the webhook) decide whether a
failed send should still let the inbound request 200 to Meta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GRAPH_API_VERSION = "v21.0"
_SEND_TIMEOUT_SECONDS = 10.0


class WhatsAppNotConfiguredError(Exception):
    """WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not set."""


class WhatsAppSendError(Exception):
    """Meta's Send Message API returned a non-2xx response."""


@dataclass(frozen=True)
class WhatsAppSendResult:
    message_id: str  # Meta's "wamid" — the correlation key for delivery-status webhooks.


async def send_text_message(to: str, body: str) -> WhatsAppSendResult:
    settings = get_settings()
    if not settings.whatsapp_token or not settings.whatsapp_phone_number_id:
        raise WhatsAppNotConfiguredError(
            "WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID must both be set in .env "
            "to send outbound WhatsApp messages."
        )

    url = (
        f"https://graph.facebook.com/{_GRAPH_API_VERSION}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}

    # Network failures and malformed responses must become WhatsAppSendError
    # too, not propagate raw — an uncaught exception here would blow past the
    # webhook's final db.commit() and lose every event recorded earlier in
    # the same Meta payload, plus return 500 (triggering Meta's aggressive
    # retry). Same rationale as each LLMProvider wrapping its own network
    # call (see app/services/llm/gemini_provider.py).
    try:
        async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp send to %s failed (network error): %s", to, exc)
        raise WhatsAppSendError(f"Network error sending to Meta: {exc}") from exc

    if response.status_code >= 300:
        logger.warning(
            "WhatsApp send failed (status=%s, to=%s): %s",
            response.status_code,
            to,
            response.text,
        )
        raise WhatsAppSendError(f"Meta returned {response.status_code}: {response.text}")

    try:
        message_id = response.json()["messages"][0]["id"]
    except (ValueError, KeyError, IndexError) as exc:
        logger.warning("WhatsApp send to %s: unexpected response shape: %s", to, response.text)
        raise WhatsAppSendError(f"Unexpected response shape from Meta: {exc}") from exc
    return WhatsAppSendResult(message_id=message_id)
