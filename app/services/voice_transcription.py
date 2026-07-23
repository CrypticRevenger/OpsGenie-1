"""Voice-note transcription — turns a WhatsApp voice note into plain text.

This module only ever produces a transcript; it never decides what to do
with it. app/api/webhooks/whatsapp.py::_handle_voice_note routes the
transcript through the exact same reply-priority ladder a typed text message
goes through (_handle_text_message) — a voice note is just another way to
produce `text`, same separation invoice_ocr.py keeps between extraction and
order_flow.py's own confidence gating.

transcribe_voice_note() never raises — same "must never raise in the webhook
path" contract app/services/assistant.py::answer_question and
app/services/invoice_ocr.py::extract_invoice_from_image both document (Meta
retries a webhook 500 aggressively against an already-dedup-committed inbound
message). A failure of any kind — no audio-capable provider configured, the
model reporting no speech, or an unexpected SDK error (Gemini's
transcribe_audio deliberately re-raises a non-5xx error as-is, same as its
generate_from_image — see that provider's own comment) — degrades to None,
and the caller shows one graceful fallback reply.
"""

from __future__ import annotations

import logging

from app.services.llm.base import AllProvidersExhaustedError
from app.services.llm.factory import transcribe_audio_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Transcribe this voice note exactly as spoken. Respond with ONLY the plain \
transcript text, in whatever language and script it was spoken in — no \
translation, no summary, no commentary, no quotation marks, no markdown \
formatting. If the recording is silent, unintelligible, or isn't speech at \
all, respond with exactly this and nothing else: NO_SPEECH_DETECTED\
"""

_NO_SPEECH_MARKER = "NO_SPEECH_DETECTED"
# A real voice note reply is at most a few sentences — a much longer response
# means the model ignored the "transcript only" instruction (e.g. it started
# narrating or answering the speech instead of transcribing it).
_MAX_TRANSCRIPT_CHARS = 2_000


async def transcribe_voice_note(audio_bytes: bytes, mime_type: str) -> str | None:
    """Best-effort transcription. Returns None when there's genuinely nothing
    usable — no audio-capable provider configured, the model reports no
    speech, or the response is implausible.
    """
    try:
        result = await transcribe_audio_with_fallback(
            system_prompt=_SYSTEM_PROMPT, audio_bytes=audio_bytes, mime_type=mime_type
        )
    except AllProvidersExhaustedError as exc:
        logger.warning("Voice note transcription: no audio-capable provider available: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - never raise into the webhook
        # Same boundary contract app/services/invoice_ocr.py's own broad
        # except documents: GeminiProvider.transcribe_audio deliberately
        # re-raises a non-5xx error as-is (a genuine 4xx from the audio API
        # itself — e.g. an unsupported codec — is "a real problem, don't
        # fall back", by design for the text-generation path too). Without
        # this, that would propagate straight out of _handle_voice_note (no
        # try/except there — it trusts this function's "never raises"
        # contract) into FastAPI's generic 500 handler, and Meta retries a
        # webhook 500 indefinitely against an inbound message whose dedup
        # row is already committed.
        logger.warning("Voice note transcription: unexpected provider failure: %s", exc)
        return None

    text = result.text.strip().strip('"')
    if not text or text == _NO_SPEECH_MARKER:
        return None
    if len(text) > _MAX_TRANSCRIPT_CHARS:
        logger.warning("Voice note transcription: response implausibly large, discarding.")
        return None
    return text
