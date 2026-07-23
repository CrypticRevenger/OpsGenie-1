"""Voice-note transcription — app/services/voice_transcription.py.

No real audio-capable provider call anywhere here — transcribe_audio_with_
fallback is monkeypatched per test, mirroring the existing convention in
tests/test_invoice_ocr.py (no network for the layer directly below the thing
under test).

    uv run pytest tests/test_voice_transcription.py -v
"""

from __future__ import annotations

import pytest
from app.services.llm.base import AllProvidersExhaustedError, ProviderResult
from app.services.voice_transcription import transcribe_voice_note


def _result(text: str) -> ProviderResult:
    return ProviderResult(
        provider="gemini", model="gemini-2.0-flash", text=text, latency_seconds=0.1
    )


def _patch(monkeypatch, result_or_exc):
    """result_or_exc: a ProviderResult, a raw response string, or an
    Exception instance to raise instead.
    """
    if isinstance(result_or_exc, str):
        result_or_exc = _result(result_or_exc)

    async def _fake_transcribe(*, system_prompt, audio_bytes, mime_type):
        if isinstance(result_or_exc, Exception):
            raise result_or_exc
        return result_or_exc

    monkeypatch.setattr(
        "app.services.voice_transcription.transcribe_audio_with_fallback", _fake_transcribe
    )


@pytest.mark.asyncio
async def test_transcribe_returns_none_when_no_provider_available(monkeypatch):
    _patch(monkeypatch, AllProvidersExhaustedError("no audio-capable provider configured"))
    result = await transcribe_voice_note(b"fake-audio-bytes", "audio/ogg")
    assert result is None


@pytest.mark.asyncio
async def test_transcribe_returns_none_on_unexpected_provider_exception(monkeypatch):
    """GeminiProvider.transcribe_audio deliberately re-raises a non-5xx
    APIStatusError as-is instead of wrapping it in ProviderUnavailableError
    (mirrors generate_from_image) — a real 4xx from the audio API itself
    (e.g. an unsupported codec) must still degrade to None here, not
    propagate into the webhook (no try/except at that call site — it trusts
    this function's documented contract) and 500 into Meta's retry loop
    against an already-dedup-committed message.
    """
    _patch(monkeypatch, RuntimeError("simulated raw 4xx from the audio API"))
    result = await transcribe_voice_note(b"fake-audio-bytes", "audio/ogg")
    assert result is None


@pytest.mark.asyncio
async def test_transcribe_returns_none_on_no_speech_marker(monkeypatch):
    _patch(monkeypatch, "NO_SPEECH_DETECTED")
    result = await transcribe_voice_note(b"fake-audio-bytes", "audio/ogg")
    assert result is None


@pytest.mark.asyncio
async def test_transcribe_returns_none_on_blank_response(monkeypatch):
    _patch(monkeypatch, "   ")
    result = await transcribe_voice_note(b"fake-audio-bytes", "audio/ogg")
    assert result is None


@pytest.mark.asyncio
async def test_transcribe_returns_none_when_response_implausibly_large(monkeypatch):
    _patch(monkeypatch, "x" * 2_001)
    result = await transcribe_voice_note(b"fake-audio-bytes", "audio/ogg")
    assert result is None


@pytest.mark.asyncio
async def test_transcribe_strips_surrounding_quotes(monkeypatch):
    _patch(monkeypatch, '"record payment"')
    result = await transcribe_voice_note(b"fake-audio-bytes", "audio/ogg")
    assert result == "record payment"


@pytest.mark.asyncio
async def test_transcribe_returns_plain_transcript(monkeypatch):
    _patch(monkeypatch, "What's my cash position today?")
    result = await transcribe_voice_note(b"fake-audio-bytes", "audio/ogg")
    assert result == "What's my cash position today?"


@pytest.mark.asyncio
async def test_transcribe_preserves_non_english_script(monkeypatch):
    # A voice note spoken in Hindi/Odia must round-trip untranslated — the
    # ladder downstream (assistant.py's own locale narration, or a
    # deterministic keyword match) is what decides what to do with it, not
    # this module.
    _patch(monkeypatch, "मेरा नकद कितना है?")
    result = await transcribe_voice_note(b"fake-audio-bytes", "audio/ogg")
    assert result == "मेरा नकद कितना है?"
