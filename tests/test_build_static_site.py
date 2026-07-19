"""scripts/build_static_site.py — the Vercel build step for the marketing
site + gate.html (the wake-gate page vercel.json's /onboard and
/dashboard/* rewrites point at). No pytest DB fixture needed: this only
renders Jinja templates to disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_static_site import (  # noqa: E402
    OUTPUT_DIR,
    RENDER_ONBOARD_URL,
    RENDER_ORIGIN,
    build,
)


def test_build_produces_gate_html_with_render_origin() -> None:
    build()
    gate_html = (OUTPUT_DIR / "gate.html").read_text(encoding="utf-8")
    assert "data-wake-gate" in gate_html
    assert f'data-render-origin="{RENDER_ORIGIN}"' in gate_html
    # gate.html is never linked to (it's a rewrite target, not a page users
    # navigate to directly) — no data-wake-redirect link should point at it.
    assert "gate.html" not in (OUTPUT_DIR / "index.html").read_text(encoding="utf-8")


def test_build_keeps_onboard_cta_links_wake_redirecting() -> None:
    build()
    index_html = (OUTPUT_DIR / "index.html").read_text(encoding="utf-8")
    assert RENDER_ONBOARD_URL in index_html
    assert "data-wake-redirect" in index_html
