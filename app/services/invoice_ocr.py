"""Invoice-photo OCR — extract a best-effort structured guess from a photo of
a paper invoice, used only to pre-fill app.services.workflows.order_flow's
existing guided flow (see that module's ocr_queue/ocr_suggestions handling).

This module never decides anything on its own — it only produces suggestions.
order_flow.py is what decides whether a suggestion is confident enough to
offer as a "reply YES" shortcut (_SUGGESTION_CONFIDENCE_THRESHOLD there); a
low-confidence or missing field here just means order_flow asks the plain
question instead, exactly as if the photo had never been sent. GST, totals,
and invoice_date are deliberately never extracted — GST/totals stay 100%
Python (compute_order_math/create_order, untouched), and nothing consumes
invoice_date yet (see [[feedback_onboarding_and_llm_direction]]'s "don't
collect what nothing uses" principle). invoice_number IS extracted despite
having no consumer yet — carried on ExtractedInvoice for a future feature
(duplicate detection, reconciliation, debugging) to read without touching
this prompt/schema again, a deliberate, narrow exception to that same rule.

extract_invoice_from_image() never raises — same "must never raise in the
webhook path" contract app/services/assistant.py::answer_question documents
(Meta retries aggressively on a 500). A failure of any kind — no vision
provider configured, a malformed/non-JSON model response, or the model
declaring the photo isn't an invoice at all — degrades to None, and the
caller (app/api/webhooks/whatsapp.py) shows one graceful fallback reply.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ValidationError, field_validator

from app.services.llm.base import AllProvidersExhaustedError
from app.services.llm.factory import extract_invoice_image_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are reading a photo of a paper sales invoice or handwritten order slip \
for a small B2B distributor. Transcribe ONLY what is actually legible in the \
image — never guess or invent a value. If a field is unclear, unreadable, or \
absent, set its "value" to null.

Respond with ONLY this JSON object, no other text, no markdown fences:

{
  "is_invoice": true or false,
  "invoice_number": {"value": string or null, "confidence": 0.0-1.0},
  "dealer_name": {"value": string or null, "confidence": 0.0-1.0},
  "items": [
    {
      "product_name": {"value": string or null, "confidence": 0.0-1.0},
      "quantity": {"value": string or null, "confidence": 0.0-1.0},
      "unit": {"value": string or null, "confidence": 0.0-1.0},
      "price": {"value": string or null, "confidence": 0.0-1.0}
    }
  ]
}

"dealer_name" is whoever the goods/invoice are being sold TO (the buyer), \
not the distributor's own business name. "quantity" and "price" values must \
be plain numbers as strings (e.g. "12", "450.50") with no currency symbols \
or commas. confidence reflects how legible/certain each specific field is —\
a crisp product name next to a smudged price should get a high confidence \
for one and a low confidence for the other, not one blended score. Set \
"is_invoice" to false if the photo clearly isn't an invoice/order document \
at all (e.g. a random object, a blank page, a different kind of document).\
"""

_MAX_JSON_RESPONSE_CHARS = 20_000


class FieldGuess(BaseModel):
    value: str | None = None
    confidence: float = 0.0


class ExtractedItem(BaseModel):
    product_name: FieldGuess = FieldGuess()
    quantity: FieldGuess = FieldGuess()
    unit: FieldGuess = FieldGuess()
    price: FieldGuess = FieldGuess()

    @field_validator("quantity", "price")
    @classmethod
    def _drop_unparseable_numeric_value(cls, guess: FieldGuess) -> FieldGuess:
        """A model can claim high confidence for a value that isn't actually
        a valid number (OCR noise, a unit mixed into the string, etc.) — never
        trust the claimed confidence over real parseability. Falls back to no
        value at all rather than raising, so one bad field never fails the
        whole extraction.
        """
        if guess.value is None:
            return guess
        try:
            Decimal(guess.value)
        except (InvalidOperation, ValueError):
            return FieldGuess(value=None, confidence=0.0)
        return guess


class ExtractedInvoice(BaseModel):
    is_invoice: bool = False
    invoice_number: FieldGuess = FieldGuess()
    dealer_name: FieldGuess = FieldGuess()
    items: list[ExtractedItem] = []


def _is_empty(extraction: ExtractedInvoice) -> bool:
    if extraction.dealer_name.value:
        return False
    return all(not item.product_name.value for item in extraction.items)


async def extract_invoice_from_image(image_bytes: bytes, mime_type: str) -> ExtractedInvoice | None:
    """Best-effort extraction. Returns None when there's genuinely nothing
    usable — the model says it isn't an invoice, no vision provider is
    configured, the response wasn't valid JSON, or every field came back
    empty. A partial/low-confidence-but-non-empty result is still returned;
    app.services.workflows.order_flow decides per-field whether a value is
    confident enough to offer as a suggestion.
    """
    try:
        result = await extract_invoice_image_with_fallback(
            system_prompt=_SYSTEM_PROMPT, image_bytes=image_bytes, mime_type=mime_type
        )
    except AllProvidersExhaustedError as exc:
        logger.warning("Invoice photo OCR: no vision provider available: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - never raise into the webhook
        # Same boundary contract app/services/assistant.py::answer_question
        # documents. Needed here too: ClaudeProvider.generate_from_image (and
        # GeminiProvider's) deliberately re-raise a non-5xx anthropic/google
        # APIStatusError as-is rather than treating it as ProviderUnavailableError
        # (see that provider's own comment — a 4xx is "a real problem, don't
        # fall back", by design for the text-generation path). Without this,
        # e.g. a photo that trips Claude's own vision-API size/format limits
        # would propagate straight out of _handle_invoice_photo (no try/except
        # there — it trusts this function's "never raises" contract) into
        # FastAPI's generic 500 handler, and Meta retries a webhook 500
        # indefinitely against an inbound message whose dedup row is already
        # committed — the same wedged-retry-loop shape already fixed once for
        # order creation (see PROJECT_STATUS.md's audit-pass entry).
        logger.warning("Invoice photo OCR: unexpected provider failure: %s", exc)
        return None

    text = result.text.strip()
    # Defensive: some models wrap JSON in markdown fences despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    if len(text) > _MAX_JSON_RESPONSE_CHARS:
        logger.warning("Invoice photo OCR: response implausibly large, discarding.")
        return None

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Invoice photo OCR: model response wasn't valid JSON: %s", exc)
        return None

    try:
        extraction = ExtractedInvoice.model_validate(raw)
    except ValidationError as exc:
        logger.warning("Invoice photo OCR: model response didn't match the expected shape: %s", exc)
        return None

    if not extraction.is_invoice or _is_empty(extraction):
        return None
    return extraction
