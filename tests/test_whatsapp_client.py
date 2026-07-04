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
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    WhatsAppSendResult,
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
