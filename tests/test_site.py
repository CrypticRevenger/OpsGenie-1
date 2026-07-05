"""Public marketing site pages — landing page, privacy, terms, contact.

uv run pytest tests/test_site.py -v
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize("path", ["/", "/privacy", "/terms", "/contact"])
@pytest.mark.asyncio
async def test_public_page_renders(client: AsyncClient, path: str) -> None:
    resp = await client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "OpsGenie" in resp.text
