"""Conservative text parser for the deterministic "if I sell N of X" fast-path.

Only ever lets the caller bypass the LLM when confident: requires an
explicit trigger phrase ("if i sell"/"if i sold"/"what if i sell") and
extracts (quantity, raw product name guess) pairs from what follows,
splitting on "and"/",". A clause with no leading number (e.g. "how much
would be left") is silently skipped — framing text, not a failed item.

Deliberately does NOT resolve product names against the real catalogue —
that needs DB access and lives in app/services/instant_reports.py's
try_deterministic_sales_impact, which trims trailing words from each raw
name guess until app/services/agent/read_tools.py's own fuzzy _find_product
matches (or gives up and returns None, falling back to the LLM). This module
only does the string-shape extraction, so it's fast to unit-test on its own.
"""

from __future__ import annotations

import re

_TRIGGER_RE = re.compile(r"if\s+i\s+(?:sell|sold)\b|what\s+if\s+i\s+sell\b", re.IGNORECASE)
_CLAUSE_SPLIT_RE = re.compile(r"\band\b|,", re.IGNORECASE)
_ITEM_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*"
    r"(?:kg|kgs|units?|pcs|pieces?|boxes?|litres?|liters?)?\s*"
    r"(?:of\s+)?(.+)$",
    re.IGNORECASE,
)


def parse_sales_impact_query(text: str) -> list[dict[str, str]] | None:
    """Returns [{"product_name": <raw guess>, "quantity_sold": <str>}, ...],
    or None if the trigger phrase is absent or no clause yields a number —
    the caller must treat None as "fall back to the LLM", never as "no
    items were sold".
    """
    trigger_match = _TRIGGER_RE.search(text)
    if trigger_match is None:
        return None

    tail = text[trigger_match.end() :]
    clauses = [c.strip() for c in _CLAUSE_SPLIT_RE.split(tail) if c.strip()]

    items: list[dict[str, str]] = []
    for clause in clauses:
        match = _ITEM_RE.match(clause)
        if match is None:
            continue
        quantity_str, name_raw = match.groups()
        name = name_raw.strip(" ?.!‘’\"'")
        if not name:
            continue
        items.append({"product_name": name, "quantity_sold": quantity_str})

    return items or None
