"""Single shared Jinja2Templates instance for every HTML-rendering route
(app/api/site.py, app/api/onboarding.py) so none of them re-instantiate their
own template loader.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
