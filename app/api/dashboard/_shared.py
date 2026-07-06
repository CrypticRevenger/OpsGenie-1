"""Small shared helpers for dashboard resource route files.

Every write action below redirects back to the company detail hub page —
this repo's dashboard has exactly one hub, not a page per resource — with an
inline error surfaced as a `?error=` query param instead of a JSON error
response, since this is a browser flow (see company_detail's error slot in
app/api/dashboard/companies.py).
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi.responses import RedirectResponse
from starlette import status


def redirect_to_company(company_id: uuid.UUID, *, error: str | None = None) -> RedirectResponse:
    url = f"/dashboard/companies/{company_id}"
    if error:
        url = f"{url}?error={quote(error)}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
