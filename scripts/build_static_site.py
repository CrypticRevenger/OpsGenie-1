"""Static-site build step for the Vercel deployment of the marketing pages.

Renders the same Jinja templates the live FastAPI app serves on Render
(app/templates/index.html, privacy.html, terms.html, contact.html) into a
plain static site under dist/ — a build artifact, never committed (see
.gitignore). Vercel runs this script itself (see vercel.json's buildCommand)
so dist/ can never drift out of sync with the templates it comes from.

Only /onboard needs an absolute URL here, since the wizard itself (and all
API/scheduler logic) stays on Render — everything else (anchors, /privacy,
/terms, /contact) stays relative because this build carries the full set of
marketing pages too.

Usage: python scripts/build_static_site.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "app" / "templates"
STATIC_DIR = REPO_ROOT / "app" / "static"
OUTPUT_DIR = REPO_ROOT / "dist"

RENDER_ONBOARD_URL = "https://opsgenie.onrender.com/onboard"

PAGES = ["index.html", "privacy.html", "terms.html", "contact.html"]


def build() -> None:
    # Import here (not at module load) so the script's own --help/inspection
    # doesn't require app.content.landing's package to already be on the path
    # in unexpected invocation contexts.
    from app.content.landing import (
        BUILT_FOR,
        COMPARISON,
        FAQ,
        HOW_IT_WORKS,
        OUTCOMES,
        PRICING_FEATURES,
    )

    context = {
        "outcomes": OUTCOMES,
        "built_for": BUILT_FOR,
        "how_it_works": HOW_IT_WORKS,
        "comparison": COMPARISON,
        "pricing_features": PRICING_FEATURES,
        "faq": FAQ,
        "onboard_url": RENDER_ONBOARD_URL,
    }

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)
    for page in PAGES:
        html = env.get_template(page).render(**context)
        (OUTPUT_DIR / page).write_text(html, encoding="utf-8")
        print(f"built dist/{page}")

    shutil.copytree(STATIC_DIR, OUTPUT_DIR / "static")
    print(f"copied {STATIC_DIR} -> dist/static")


if __name__ == "__main__":
    import sys

    # Make the repo root importable so `from app.content.landing import ...`
    # works when this script is invoked directly (python scripts/build_static_site.py)
    # rather than as an installed package — this is exactly how Vercel's
    # buildCommand runs it.
    sys.path.insert(0, str(REPO_ROOT))
    build()
