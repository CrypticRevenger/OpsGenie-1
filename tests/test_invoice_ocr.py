"""Invoice-photo OCR extraction — app/services/invoice_ocr.py.

No real vision-provider call anywhere here — extract_invoice_image_with_
fallback is monkeypatched per test, mirroring the existing convention in
tests/test_whatsapp_client.py (no network for the layer directly below the
thing under test).

    uv run pytest tests/test_invoice_ocr.py -v
"""

from __future__ import annotations

import json

import pytest
from app.services.invoice_ocr import extract_invoice_from_image
from app.services.llm.base import AllProvidersExhaustedError, ProviderResult


def _result_text(text: str) -> ProviderResult:
    return ProviderResult(
        provider="anthropic", model="claude-haiku-4-5", text=text, latency_seconds=0.1
    )


def _fake_result(payload: dict) -> ProviderResult:
    return _result_text(json.dumps(payload))


def _guess(value, confidence=0.9):
    return {"value": value, "confidence": confidence}


def _patch(monkeypatch, result_or_exc):
    """result_or_exc: a ProviderResult, a raw response string, or an
    Exception instance to raise instead.
    """
    if isinstance(result_or_exc, str):
        result_or_exc = _result_text(result_or_exc)

    async def _fake_extract(*, system_prompt, image_bytes, mime_type):
        if isinstance(result_or_exc, Exception):
            raise result_or_exc
        return result_or_exc

    monkeypatch.setattr(
        "app.services.invoice_ocr.extract_invoice_image_with_fallback", _fake_extract
    )


@pytest.mark.asyncio
async def test_extract_returns_none_when_no_provider_available(monkeypatch):
    _patch(monkeypatch, AllProvidersExhaustedError("no vision provider configured"))
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is None


@pytest.mark.asyncio
async def test_extract_returns_none_on_unexpected_provider_exception(monkeypatch):
    """Claude/Gemini's generate_from_image deliberately re-raises a non-5xx
    APIStatusError as-is instead of wrapping it in ProviderUnavailableError
    (see claude_provider.py's own comment) — a real 4xx from the vision API
    itself (e.g. an image tripping its own size/format limits) must still
    degrade to None here, not propagate into the webhook (no try/except at
    that call site — it trusts this function's documented contract) and 500
    into Meta's retry loop against an already-dedup-committed message."""
    _patch(monkeypatch, RuntimeError("simulated raw 4xx from the vision API"))
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is None


@pytest.mark.asyncio
async def test_extract_returns_none_on_invalid_json(monkeypatch):
    _patch(monkeypatch, "not valid json {{{")
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is None


@pytest.mark.asyncio
async def test_extract_returns_none_when_is_invoice_false(monkeypatch):
    _patch(
        monkeypatch,
        _fake_result(
            {
                "is_invoice": False,
                "invoice_number": _guess(None, 0.0),
                "dealer_name": _guess("Ram Traders"),
                "items": [],
            }
        ),
    )
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is None


@pytest.mark.asyncio
async def test_extract_returns_none_when_completely_empty(monkeypatch):
    _patch(
        monkeypatch,
        _fake_result(
            {
                "is_invoice": True,
                "invoice_number": _guess(None, 0.0),
                "dealer_name": _guess(None, 0.0),
                "items": [{"product_name": _guess(None, 0.0)}],
            }
        ),
    )
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is None


@pytest.mark.asyncio
async def test_extract_returns_partial_result_dealer_only(monkeypatch):
    _patch(
        monkeypatch,
        _fake_result(
            {
                "is_invoice": True,
                "invoice_number": _guess(None, 0.0),
                "dealer_name": _guess("Ram Traders", 0.95),
                "items": [],
            }
        ),
    )
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is not None
    assert result.dealer_name.value == "Ram Traders"
    assert result.items == []


@pytest.mark.asyncio
async def test_extract_returns_partial_result_items_only(monkeypatch):
    _patch(
        monkeypatch,
        _fake_result(
            {
                "is_invoice": True,
                "invoice_number": _guess(None, 0.0),
                "dealer_name": _guess(None, 0.0),
                "items": [
                    {
                        "product_name": _guess("Chocolate Milk"),
                        "quantity": _guess("12"),
                        "unit": _guess("box"),
                        "price": _guess("450"),
                    }
                ],
            }
        ),
    )
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is not None
    assert result.dealer_name.value is None
    assert len(result.items) == 1
    assert result.items[0].product_name.value == "Chocolate Milk"


@pytest.mark.asyncio
async def test_extract_full_result_carries_invoice_number_unused(monkeypatch):
    """invoice_number is extracted but nothing downstream consumes it yet —
    see the module docstring; this just confirms it round-trips.
    """
    _patch(
        monkeypatch,
        _fake_result(
            {
                "is_invoice": True,
                "invoice_number": _guess("INV-1047", 0.8),
                "dealer_name": _guess("Ram Traders", 0.95),
                "items": [
                    {
                        "product_name": _guess("Chocolate Milk", 0.9),
                        "quantity": _guess("12", 0.85),
                        "unit": _guess("box", 0.6),
                        "price": _guess("450", 0.4),
                    }
                ],
            }
        ),
    )
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is not None
    assert result.invoice_number.value == "INV-1047"
    assert result.items[0].price.confidence == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_extract_strips_markdown_fences(monkeypatch):
    payload = {
        "is_invoice": True,
        "invoice_number": _guess(None, 0.0),
        "dealer_name": _guess("Ram Traders", 0.9),
        "items": [],
    }
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    _patch(monkeypatch, fenced)
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is not None
    assert result.dealer_name.value == "Ram Traders"


@pytest.mark.asyncio
async def test_unparseable_numeric_value_dropped_regardless_of_claimed_confidence(monkeypatch):
    """A model claiming high confidence for a garbled non-numeric quantity/
    price must never be trusted over actual Decimal-parseability.
    """
    _patch(
        monkeypatch,
        _fake_result(
            {
                "is_invoice": True,
                "invoice_number": _guess(None, 0.0),
                "dealer_name": _guess("Ram Traders", 0.9),
                "items": [
                    {
                        "product_name": _guess("Chocolate Milk", 0.9),
                        "quantity": _guess("about a dozen", 0.99),
                        "unit": _guess("box", 0.9),
                        "price": _guess(None, 0.0),
                    }
                ],
            }
        ),
    )
    result = await extract_invoice_from_image(b"fake-bytes", "image/jpeg")
    assert result is not None
    item = result.items[0]
    assert item.quantity.value is None
    assert item.quantity.confidence == 0.0
