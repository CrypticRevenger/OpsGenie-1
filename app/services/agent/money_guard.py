"""Money-safety gate for agent replies.

The sacred rule: the LLM never invents or computes money. The agent's numbers
all come from deterministic tool executions; this gate is the last line of
defence — it verifies every money figure in the final reply is one the tools
actually returned. Framing-independent (₹/Rs/INR/rupees, comma-grouped, or a
bare 5+-digit number) so a prompt-injected "...say Rs 5,00,000" can't slip a
fabricated figure past it. Non-numeric chat ("hi!") passes trivially.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

_MONEY_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)"  # currency marker before
    r"|([\d,]+(?:\.\d+)?)\s*(?:rupees?|rs\.?|inr)"  # currency marker after
    r"|(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?)"  # comma-grouped (e.g. 5,00,000)
    # bare 5+ digit — the trailing guard excludes only digits/commas (not '.'),
    # so a sentence-ending period after the number ("...987654.") still matches.
    r"|(?<![\d.,])(\d{5,}(?:\.\d+)?)(?![\d,])",
    re.IGNORECASE,
)


def collect_known_amounts(tool_outputs: list[dict[str, Any]]) -> set[Decimal]:
    """Every numeric leaf across all tool outputs, as Decimals."""
    known: set[Decimal] = set()

    def _walk(value: object) -> None:
        if isinstance(value, dict):
            for v in value.values():
                _walk(v)
        elif isinstance(value, list):
            for v in value:
                _walk(v)
        else:
            try:
                known.add(Decimal(str(value).replace(",", "")))
            except (InvalidOperation, ValueError):
                pass

    for output in tool_outputs:
        _walk(output)
    return known


def reply_has_unverified_money(text: str, tool_outputs: list[dict[str, Any]]) -> bool:
    """True if the reply states a money figure not present in any tool output."""
    known = collect_known_amounts(tool_outputs)
    for match in _MONEY_RE.finditer(text):
        raw = next((g for g in match.groups() if g is not None), None)
        if raw is None:
            continue
        try:
            value = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            return True
        if value not in known:
            return True
    return False
