"""WhatsApp outbound sending — Phase 8 (text) + onboarding (template).

Fail-closed, same convention as admin_api_key / whatsapp_app_secret / each
LLMProvider's NoApiKeyConfiguredError: an unconfigured token/phone number ID
raises rather than silently no-op-ing. Callers (the webhook) decide whether a
failed send should still let the inbound request 200 to Meta.

Message shapes:
- send_text_message: free-form text, only deliverable inside the 24h customer-
  service window (the user messaged first). Used for menu replies, follow-ups,
  notifications.
- send_interactive_list_message: a tappable list of up to 10 options, same 24h
  window as text. Used for the "menu" quick-launch command so a distributor
  can tap "Cash Position" instead of typing "cash".
- send_document_message: a free-form document (e.g. a generated PDF), same
  24h window as text — unlike send_template_message's document header, this
  only works on a number already mid-conversation. Used to hand a PDF
  straight to the founder's own chat when the invoice's real recipient
  (dealer/supplier) can't be reached directly (see
  app/services/invoice_delivery.py).
- send_template_message: a Meta-approved template, the only thing deliverable
  to a number that hasn't messaged first. Used for the onboarding welcome and
  (V0.2, with a document header) sending an invoice PDF to a dealer, who has
  essentially never messaged the distributor's WhatsApp number first.
- upload_media: uploads binary content (e.g. a generated invoice PDF) to
  Meta's Media API, returning a media id a template's document header can
  reference — a template's header component doesn't need the actual document
  content declared at template-creation time, just its type.
- download_media: the inbound counterpart — resolves an inbound message's
  media id (e.g. a photographed invoice) to its actual bytes, for the
  invoice-photo OCR path (app/services/invoice_ocr.py). Meta's Media API is
  two calls: GET /{media_id} for a short-lived signed URL, then GET that URL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GRAPH_API_VERSION = "v21.0"
_SEND_TIMEOUT_SECONDS = 10.0
_MEDIA_DOWNLOAD_TIMEOUT_SECONDS = 30.0
# Mirrors app/api/admin/imports.py's existing 10MB upload cap — an inbound
# photo has no reason to be larger, and this bounds how much a single
# webhook request reads into memory.
_MAX_MEDIA_DOWNLOAD_BYTES = 10 * 1024 * 1024
# Meta rejects a text message body over this outright (400 "Param text.body
# must be at most 4096 characters long") — a real production failure,
# 2026-07-24: some reply exceeded it, the send failed, and the founder got
# nothing at all instead of a message. Every known caller already tries to
# stay well under this (e.g. instant_reports.py's _LIST_REPLY_CAP), so this
# should rarely trigger — it's a last-resort safety net for whichever caller
# doesn't (or a future one), so an oversized reply is truncated rather than
# silently dropped entirely.
_MAX_TEXT_BODY_CHARS = 4096
_TRUNCATION_SUFFIX = "\n\n… (message truncated — too long for WhatsApp)"


class WhatsAppNotConfiguredError(Exception):
    """WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not set."""


class WhatsAppSendError(Exception):
    """Meta's Send Message API returned a non-2xx response."""


class WhatsAppMediaTooLargeError(Exception):
    """An inbound media download exceeded _MAX_MEDIA_DOWNLOAD_BYTES."""


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
    if len(body) > _MAX_TEXT_BODY_CHARS:
        logger.warning(
            "WhatsApp text body to %s is %d chars, over Meta's %d-char limit — truncating.",
            to,
            len(body),
            _MAX_TEXT_BODY_CHARS,
        )
        body = body[: _MAX_TEXT_BODY_CHARS - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX
    return await _post_message(
        {"messaging_product": "whatsapp", "type": "text", "text": {"body": body}}, to
    )


async def send_interactive_list_message(
    to: str,
    *,
    body: str,
    button_text: str,
    sections: list[dict],
) -> WhatsAppSendResult:
    """A tappable list message — Meta caps this at 10 rows total across all
    `sections` (each a {"title": str, "rows": [{"id", "title", "description"}]}
    dict). Tapping a row delivers an inbound `type: interactive` message whose
    `list_reply.id` the webhook reads exactly like typed text (see
    app/api/webhooks/whatsapp.py's _extract_text_body), so every row's `id`
    must be a string one of the existing command registries/keywords already
    understands.
    """
    return await _post_message(
        {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {"button": button_text, "sections": sections},
            },
        },
        to,
    )


async def send_document_message(
    to: str, media_id: str, filename: str, *, caption: str | None = None
) -> WhatsAppSendResult:
    """Free-form document message — only deliverable inside the 24h customer-
    service window (same constraint as send_text_message), unlike
    send_template_message's document header which works outside it.
    """
    document: dict = {"id": media_id, "filename": filename}
    if caption:
        document["caption"] = caption
    return await _post_message(
        {"messaging_product": "whatsapp", "type": "document", "document": document}, to
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


async def download_media(media_id: str) -> tuple[bytes, str]:
    """Download an inbound media message's actual bytes + mime type. Two Graph
    API calls: GET /{media_id} resolves a short-lived signed URL (the same
    bearer token also authorizes the URL fetch itself, per Meta's docs), then
    GET that URL for the content. Same fail-closed/error-wrapping contract as
    every other function here.
    """
    settings = get_settings()
    if not settings.whatsapp_token or not settings.whatsapp_phone_number_id:
        raise WhatsAppNotConfiguredError(
            "WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID must both be set in .env "
            "to download inbound WhatsApp media."
        )

    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    lookup_url = f"https://graph.facebook.com/{_GRAPH_API_VERSION}/{media_id}"

    try:
        async with httpx.AsyncClient(timeout=_MEDIA_DOWNLOAD_TIMEOUT_SECONDS) as client:
            lookup_response = await client.get(lookup_url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp media lookup failed (network error): %s", exc)
        raise WhatsAppSendError(f"Network error looking up media from Meta: {exc}") from exc

    if lookup_response.status_code >= 300:
        logger.warning(
            "WhatsApp media lookup failed (status=%s): %s",
            lookup_response.status_code,
            lookup_response.text,
        )
        raise WhatsAppSendError(
            f"Meta returned {lookup_response.status_code}: {lookup_response.text}"
        )

    try:
        media_info = lookup_response.json()
        media_url = media_info["url"]
    except (ValueError, KeyError) as exc:
        logger.warning("WhatsApp media lookup: unexpected response shape: %s", lookup_response.text)
        raise WhatsAppSendError(f"Unexpected response shape from Meta: {exc}") from exc

    mime_type = media_info.get("mime_type", "application/octet-stream")
    reported_size = media_info.get("file_size")
    if isinstance(reported_size, int) and reported_size > _MAX_MEDIA_DOWNLOAD_BYTES:
        raise WhatsAppMediaTooLargeError(
            f"Media {media_id} reports {reported_size} bytes, over the "
            f"{_MAX_MEDIA_DOWNLOAD_BYTES} byte limit."
        )

    try:
        async with httpx.AsyncClient(timeout=_MEDIA_DOWNLOAD_TIMEOUT_SECONDS) as client:
            file_response = await client.get(media_url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp media download failed (network error): %s", exc)
        raise WhatsAppSendError(f"Network error downloading media from Meta: {exc}") from exc

    if file_response.status_code >= 300:
        logger.warning("WhatsApp media download failed (status=%s).", file_response.status_code)
        raise WhatsAppSendError(f"Meta returned {file_response.status_code} downloading media.")

    content = file_response.content
    if len(content) > _MAX_MEDIA_DOWNLOAD_BYTES:
        raise WhatsAppMediaTooLargeError(
            f"Media {media_id} downloaded {len(content)} bytes, over the "
            f"{_MAX_MEDIA_DOWNLOAD_BYTES} byte limit."
        )
    return content, mime_type
