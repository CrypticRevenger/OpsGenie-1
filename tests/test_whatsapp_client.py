"""WhatsAppClient (outbound sending) tests — Phase 8.

No real network call anywhere here — httpx.AsyncClient.post and get_settings
are both monkeypatched per test, including the "not configured" case. Real
Meta credentials were added to .env once the user set up their Meta developer
account (Phase 9), so these tests can no longer rely on the real environment
being unconfigured — they force the specific settings state each case needs.
"""

from __future__ import annotations

import httpx
import pytest
from app.services.whatsapp_client import (
    WhatsAppMediaTooLargeError,
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    WhatsAppSendResult,
    download_media,
    send_interactive_list_message,
    send_template_message,
    send_text_message,
)


@pytest.mark.asyncio
async def test_send_text_message_raises_when_not_configured(monkeypatch):
    class _Settings:
        whatsapp_token = None
        whatsapp_phone_number_id = None

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    with pytest.raises(WhatsAppNotConfiguredError):
        await send_text_message("+919999999999", "hello")


@pytest.mark.asyncio
async def test_send_text_message_success(monkeypatch):
    captured_urls = []

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"messages": [{"id": "wamid.ABC123"}]}

    async def _fake_post(self, url, json, headers):
        captured_urls.append(url)
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    class _Settings:
        whatsapp_token = "fake-token"
        whatsapp_phone_number_id = "123456"

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    result = await send_text_message("+919999999999", "hello")
    assert isinstance(result, WhatsAppSendResult)
    assert result.message_id == "wamid.ABC123"
    assert captured_urls[0].endswith("123456/messages")


@pytest.mark.asyncio
async def test_send_text_message_raises_on_non_2xx(monkeypatch):
    class _FakeResponse:
        status_code = 400
        text = '{"error": {"message": "Invalid recipient"}}'

        def json(self):
            return {}

    async def _fake_post(self, url, json, headers):
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    class _Settings:
        whatsapp_token = "fake-token"
        whatsapp_phone_number_id = "123456"

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    with pytest.raises(WhatsAppSendError):
        await send_text_message("+919999999999", "hello")


@pytest.mark.asyncio
async def test_send_text_message_wraps_network_error(monkeypatch):
    """A raw httpx.ConnectError/ReadTimeout must never escape as-is — it would
    propagate past the webhook's final db.commit() and return 500 to Meta.
    """

    async def _fake_post(self, url, json, headers):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    class _Settings:
        whatsapp_token = "fake-token"
        whatsapp_phone_number_id = "123456"

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    with pytest.raises(WhatsAppSendError):
        await send_text_message("+919999999999", "hello")


@pytest.mark.asyncio
async def test_send_text_message_wraps_malformed_response(monkeypatch):
    """A 2xx response whose body doesn't have the expected messages[0].id
    shape must also become a WhatsAppSendError, not a raw KeyError/IndexError.
    """

    class _FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    async def _fake_post(self, url, json, headers):
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    class _Settings:
        whatsapp_token = "fake-token"
        whatsapp_phone_number_id = "123456"

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    with pytest.raises(WhatsAppSendError):
        await send_text_message("+919999999999", "hello")


# ── send_template_message (onboarding welcome) ────────────────────────────────


@pytest.mark.asyncio
async def test_send_template_message_success(monkeypatch):
    captured = {}

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"messages": [{"id": "wamid.TMPL1"}]}

    async def _fake_post(self, url, json, headers):
        captured["payload"] = json
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    class _Settings:
        whatsapp_token = "fake-token"
        whatsapp_phone_number_id = "123456"

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    result = await send_template_message("+919999999999", "welcome", "en_US")
    assert isinstance(result, WhatsAppSendResult)
    assert result.message_id == "wamid.TMPL1"
    assert captured["payload"]["type"] == "template"
    assert captured["payload"]["template"]["name"] == "welcome"
    assert captured["payload"]["template"]["language"]["code"] == "en_US"
    assert "components" not in captured["payload"]["template"]  # no body params


@pytest.mark.asyncio
async def test_send_template_message_with_body_params(monkeypatch):
    captured = {}

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"messages": [{"id": "wamid.TMPL2"}]}

    async def _fake_post(self, url, json, headers):
        captured["payload"] = json
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    class _Settings:
        whatsapp_token = "fake-token"
        whatsapp_phone_number_id = "123456"

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    await send_template_message("+919999999999", "welcome", "en_US", body_params=["Spandan"])
    comps = captured["payload"]["template"]["components"]
    assert comps[0]["type"] == "body"
    assert comps[0]["parameters"][0]["text"] == "Spandan"


@pytest.mark.asyncio
async def test_send_template_message_raises_when_not_configured(monkeypatch):
    class _Settings:
        whatsapp_token = None
        whatsapp_phone_number_id = None

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    with pytest.raises(WhatsAppNotConfiguredError):
        await send_template_message("+919999999999", "welcome", "en_US")


# ── send_interactive_list_message (tappable "menu" command) ─────────────────


@pytest.mark.asyncio
async def test_send_interactive_list_message_success(monkeypatch):
    captured = {}

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"messages": [{"id": "wamid.LIST1"}]}

    async def _fake_post(self, url, json, headers):
        captured["payload"] = json
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    class _Settings:
        whatsapp_token = "fake-token"
        whatsapp_phone_number_id = "123456"

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    sections = [{"title": "Reports", "rows": [{"id": "cash", "title": "Cash Position"}]}]
    result = await send_interactive_list_message(
        "+919999999999", body="Pick one", button_text="Choose", sections=sections
    )
    assert isinstance(result, WhatsAppSendResult)
    assert result.message_id == "wamid.LIST1"
    payload = captured["payload"]
    assert payload["type"] == "interactive"
    assert payload["interactive"]["type"] == "list"
    assert payload["interactive"]["body"]["text"] == "Pick one"
    assert payload["interactive"]["action"]["button"] == "Choose"
    assert payload["interactive"]["action"]["sections"] == sections


@pytest.mark.asyncio
async def test_send_interactive_list_message_raises_when_not_configured(monkeypatch):
    class _Settings:
        whatsapp_token = None
        whatsapp_phone_number_id = None

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    with pytest.raises(WhatsAppNotConfiguredError):
        await send_interactive_list_message(
            "+919999999999", body="Pick one", button_text="Choose", sections=[]
        )


# ── download_media (invoice-photo OCR inbound path) ──────────────────────────


def _configured_settings():
    class _Settings:
        whatsapp_token = "fake-token"
        whatsapp_phone_number_id = "123456"

    return _Settings()


@pytest.mark.asyncio
async def test_download_media_success(monkeypatch):
    calls = []

    class _LookupResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "url": "https://lookaside.fbsbx.com/whatsapp_business/media/fake",
                "mime_type": "image/jpeg",
                "file_size": 12,
            }

    class _FileResponse:
        status_code = 200
        content = b"fake-image-bytes"

    async def _fake_get(self, url, headers):
        calls.append(url)
        if url.endswith("MEDIA_ID_1"):
            return _LookupResponse()
        return _FileResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr("app.services.whatsapp_client.get_settings", _configured_settings)

    content, mime_type = await download_media("MEDIA_ID_1")
    assert content == b"fake-image-bytes"
    assert mime_type == "image/jpeg"
    assert calls[0].endswith("MEDIA_ID_1")
    assert calls[1].startswith("https://lookaside.fbsbx.com/")


@pytest.mark.asyncio
async def test_download_media_raises_when_not_configured(monkeypatch):
    class _Settings:
        whatsapp_token = None
        whatsapp_phone_number_id = None

    monkeypatch.setattr("app.services.whatsapp_client.get_settings", lambda: _Settings())

    with pytest.raises(WhatsAppNotConfiguredError):
        await download_media("MEDIA_ID_1")


@pytest.mark.asyncio
async def test_download_media_raises_on_oversized_reported_file_size(monkeypatch):
    class _LookupResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "url": "https://lookaside.fbsbx.com/whatsapp_business/media/fake",
                "mime_type": "image/jpeg",
                "file_size": 999_999_999,
            }

    async def _fake_get(self, url, headers):
        return _LookupResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr("app.services.whatsapp_client.get_settings", _configured_settings)

    with pytest.raises(WhatsAppMediaTooLargeError):
        await download_media("MEDIA_ID_1")


@pytest.mark.asyncio
async def test_download_media_raises_on_oversized_actual_bytes(monkeypatch):
    """The reported file_size can't be trusted alone — the actual downloaded
    length is checked too.
    """

    class _LookupResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "url": "https://lookaside.fbsbx.com/whatsapp_business/media/fake",
                "mime_type": "image/jpeg",
                # No file_size reported at all — some responses omit it.
            }

    class _FileResponse:
        status_code = 200
        content = b"x" * (11 * 1024 * 1024)

    async def _fake_get(self, url, headers):
        if url.endswith("MEDIA_ID_1"):
            return _LookupResponse()
        return _FileResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr("app.services.whatsapp_client.get_settings", _configured_settings)

    with pytest.raises(WhatsAppMediaTooLargeError):
        await download_media("MEDIA_ID_1")


@pytest.mark.asyncio
async def test_download_media_wraps_malformed_lookup_response(monkeypatch):
    class _LookupResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}  # missing "url"

    async def _fake_get(self, url, headers):
        return _LookupResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr("app.services.whatsapp_client.get_settings", _configured_settings)

    with pytest.raises(WhatsAppSendError):
        await download_media("MEDIA_ID_1")


@pytest.mark.asyncio
async def test_download_media_wraps_network_error(monkeypatch):
    async def _fake_get(self, url, headers):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr("app.services.whatsapp_client.get_settings", _configured_settings)

    with pytest.raises(WhatsAppSendError):
        await download_media("MEDIA_ID_1")


@pytest.mark.asyncio
async def test_download_media_raises_on_non_2xx_lookup(monkeypatch):
    class _LookupResponse:
        status_code = 404
        text = '{"error": "not found"}'

    async def _fake_get(self, url, headers):
        return _LookupResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr("app.services.whatsapp_client.get_settings", _configured_settings)

    with pytest.raises(WhatsAppSendError):
        await download_media("MEDIA_ID_1")
