"""WhatsApp outbound sending — Phase 8 (text) + onboarding (template).

Fail-closed, same convention as admin_api_key / whatsapp_app_secret / each
LLMProvider's NoApiKeyConfiguredError: an unconfigured token/phone number ID
raises rather than silently no-op-ing. Callers (the webhook) decide whether a
failed send should still let the inbound request 200 to Meta.

Message shapes:
- send_text_message: free-form text, only deliverable inside the 24h customer-
  service window (the user messaged first). Used for menu replies, follow-ups,
  notifications.
- send_template_message: a Meta-approved template, the only thing deliverable
  to a number that hasn't messaged first. Used for the onboarding welcome and
  (V0.2, with a document header) sending an invoice PDF to a dealer, who has
  essentially never messaged the distributor's WhatsApp number first.
- upload_media: uploads binary content (e.g. a generated invoice PDF) to
  Meta's Media API, returning a media id a template's document header can
  reference — a template's header component doesn't need the actual document
  content declared at template-creation time, just its type.
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


async def _post_message(payload: dict, to: str) -> WhatsAppSendResult:
    """Shared POST to Meta's messages endpoint. Both fail-closed on missing
    credentials and error-wrapped (network + malformed response) so callers
    only ever have to handle WhatsAppNotConfiguredError / WhatsAppSendError —
    a raw exception here would blow past a webhook's final db.commit() and
    return 500 (triggering Meta's aggressive retry).
    """
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
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}

    try:
        async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json={**payload, "to": to}, headers=headers)
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


async def send_text_message(to: str, body: str) -> WhatsAppSendResult:
    return await _post_message(
        {"messaging_product": "whatsapp", "type": "text", "text": {"body": body}}, to
    )


async def send_template_message(
    to: str,
    template_name: str,
    language_code: str,
    body_params: list[str] | None = None,
    header_media_id: str | None = None,
    header_filename: str | None = None,
) -> WhatsAppSendResult:
    """Send a Meta-approved template. body_params fills the template's {{1}},
    {{2}}, ... body variables in order (omit for a no-variable template).
    header_media_id (paired with header_filename) fills a template whose
    header component is declared as a document — used for the invoice-PDF
    template (see app/services/invoice_delivery.py). The document's actual
    bytes are uploaded separately via upload_media(); only the resulting
    media id is referenced here.
    """
    template: dict = {"name": template_name, "language": {"code": language_code}}
    components: list[dict] = []
    if header_media_id:
        components.append(
            {
                "type": "header",
                "parameters": [
                    {
                        "type": "document",
                        "document": {"id": header_media_id, "filename": header_filename},
                    }
                ],
            }
        )
    if body_params:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params],
            }
        )
    if components:
        template["components"] = components
    return await _post_message(
        {"messaging_product": "whatsapp", "type": "template", "template": template}, to
    )


async def upload_media(file_bytes: bytes, filename: str, mime_type: str) -> str:
    """Upload binary content to Meta's Media API, returning a media id a
    template's document header (or a free-form document message) can
    reference. Same fail-closed contract as _post_message.
    """
    settings = get_settings()
    if not settings.whatsapp_token or not settings.whatsapp_phone_number_id:
        raise WhatsAppNotConfiguredError(
            "WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID must both be set in .env "
            "to upload WhatsApp media."
        )

    url = (
        f"https://graph.facebook.com/{_GRAPH_API_VERSION}/"
        f"{settings.whatsapp_phone_number_id}/media"
    )
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    files = {"file": (filename, file_bytes, mime_type)}
    data = {"messaging_product": "whatsapp", "type": mime_type}

    try:
        async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_SECONDS) as client:
            response = await client.post(url, files=files, data=data, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp media upload failed (network error): %s", exc)
        raise WhatsAppSendError(f"Network error uploading media to Meta: {exc}") from exc

    if response.status_code >= 300:
        logger.warning(
            "WhatsApp media upload failed (status=%s): %s",
            response.status_code,
            response.text,
        )
        raise WhatsAppSendError(f"Meta returned {response.status_code}: {response.text}")

    try:
        return response.json()["id"]
    except (ValueError, KeyError) as exc:
        logger.warning("WhatsApp media upload: unexpected response shape: %s", response.text)
        raise WhatsAppSendError(f"Unexpected response shape from Meta: {exc}") from exc
