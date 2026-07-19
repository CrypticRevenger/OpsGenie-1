"""Pytest bootstrap + shared fixtures.

Test isolation (why this file does env surgery *before* importing app):

- Tests run against a DEDICATED database (``<dbname>_test``), never the working
  ``opsgenie`` dev DB. Many tests call ``db.commit()`` directly; without a
  separate DB those committed rows pile up in the dev database forever and the
  real scheduler then fires founder alerts about hundreds of leftover fixture
  companies. A separate DB + truncation between tests keeps the dev data clean.
- Real outbound WhatsApp credentials + FOUNDER_WHATSAPP_NUMBER live in .env, and
  SCHEDULER_ENABLED is true there. We blank all of them for the test process so
  no test — including any that drives the real scheduler tick / stale-data
  digest — can ever hit Meta's API or blast the founder's real phone.

The engine is built at ``app.db.session`` import time from ``get_settings()``,
so the environment must be rewritten and the settings cache cleared *before* the
first ``app.*`` import below.
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _derive_test_url(real_url: str) -> str:
    parts = urlsplit(real_url)
    dbname = parts.path.lstrip("/")
    if not dbname.endswith("_test"):
        dbname = f"{dbname}_test"
    return urlunsplit(parts._replace(path=f"/{dbname}"))


# ── Rewrite the environment before the app (and its engine) are imported ──────
from app.core.config import get_settings  # noqa: E402  (must precede other app imports)

_REAL_DB_URL = str(get_settings().database_url)
TEST_DB_URL = _derive_test_url(_REAL_DB_URL)

# ── Production tripwire ───────────────────────────────────────────────────────
# The suite CREATEs, migrates, and TRUNCATEs its target database (see fixtures
# below), so that target must never be production infrastructure. The _test
# suffix already redirects the database *name*, but assert it — and refuse any
# non-local host unless explicitly opted in — so a fat-fingered DATABASE_URL
# (e.g. the live prod Neon URL uncommented in .env) can never repeat the
# incident where the test suite populated the production DB with 1,000+ fixture
# companies and blasted the founder's real WhatsApp. Run tests against a local
# Postgres; set ALLOW_REMOTE_TEST_DB=1 only for a deliberate remote *_test DB.
_test_db_name = urlsplit(TEST_DB_URL).path.lstrip("/")
_test_db_host = urlsplit(TEST_DB_URL).hostname or ""
if not _test_db_name.endswith("_test"):
    raise RuntimeError(f"Refusing to run tests: {_test_db_name!r} is not a *_test database.")
if _test_db_host not in {"localhost", "127.0.0.1", "::1", ""} and (
    os.environ.get("ALLOW_REMOTE_TEST_DB") != "1"
):
    raise RuntimeError(
        f"Refusing to run the test suite against remote DB host {_test_db_host!r}: the "
        "suite CREATEs/migrates/TRUNCATEs its target DB. Tests once ran against the "
        "production Neon DB and polluted it with 1,000+ fixture companies. Point "
        "DATABASE_URL at a local Postgres, or set ALLOW_REMOTE_TEST_DB=1 if you truly "
        "intend a remote *_test database."
    )

os.environ["DATABASE_URL"] = TEST_DB_URL
# Fail-closed the outbound side for the whole test run (empty string is falsy,
# so every `if not settings.x` guard treats these as unset).
os.environ["WHATSAPP_TOKEN"] = ""
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = ""
os.environ["FOUNDER_WHATSAPP_NUMBER"] = ""
os.environ["SCHEDULER_ENABLED"] = "false"
get_settings.cache_clear()  # next get_settings() picks up the test environment

# ── Guarded jiter shim ────────────────────────────────────────────────────────
# The compiled `jiter` extension is blocked by Windows Application Control on
# some dev machines. `app.main` (imported below) pulls in `anthropic`, which does
# `import jiter` at module load and only ever calls `jiter.from_json`. When the
# real module can't load, install a minimal pure-Python stand-in so test
# collection isn't blocked. Completely inert wherever real jiter imports fine
# (CI, production, unblocked machines).
try:
    import jiter  # noqa: F401,E402
except Exception:  # pragma: no cover — only triggers where the DLL is blocked
    import json as _json
    import types as _types

    _jiter_stub = _types.ModuleType("jiter")

    def _stub_from_json(data, **_kwargs):
        if isinstance(data, (bytes, bytearray)):
            data = data.decode("utf-8")
        return _json.loads(data)

    class _LosslessFloat(float):
        def __new__(cls, value):
            return super().__new__(cls, float(value))

    _jiter_stub.from_json = _stub_from_json
    _jiter_stub.cache_clear = lambda: None
    _jiter_stub.cache_usage = lambda: 0
    _jiter_stub.LosslessFloat = _LosslessFloat
    sys.modules["jiter"] = _jiter_stub

import app.models  # noqa: E402,F401 — register every ORM model on Base.metadata
from app.db.base import Base  # noqa: E402
from app.db.session import async_session_factory, engine  # noqa: E402
from app.main import app  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402


def has_any_llm_key_configured() -> bool:
    """True if at least one of the 4 LLM provider keys is set in .env — used
    to gate tests that make a real network call to whichever provider the
    fallback chain actually reaches, rather than hardcoding one provider.
    """
    settings = get_settings()
    return any(
        [
            settings.anthropic_api_key,
            settings.gemini_api_key,
            settings.groq_api_key,
            settings.openrouter_api_key,
        ]
    )


def _maintenance_dsn_and_dbname(async_url: str) -> tuple[str, str]:
    """A plain (non-asyncpg-driver) DSN pointing at the server's default
    ``postgres`` database, plus the target test DB name — used to CREATE the
    test database itself, which can't be done from inside a connection to it.
    """
    parts = urlsplit(async_url.replace("+asyncpg", ""))
    dbname = parts.path.lstrip("/")
    maintenance = urlunsplit(parts._replace(path="/postgres"))
    return maintenance, dbname


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """Create the dedicated test database if missing and migrate it to head
    with the real Alembic migrations (faithful schema, including migration-only
    indexes). Runs once per session, before any test touches the engine.
    """
    import asyncio

    async def _ensure_database() -> None:
        maintenance_dsn, dbname = _maintenance_dsn_and_dbname(TEST_DB_URL)
        conn = await asyncpg.connect(maintenance_dsn)
        try:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dbname)
            if not exists:
                await conn.execute(f'CREATE DATABASE "{dbname}"')
        finally:
            await conn.close()

    asyncio.run(_ensure_database())

    # Migrate via subprocess: Alembic's env.py drives its own asyncio loop, which
    # can't be nested inside pytest-asyncio's. The subprocess inherits DATABASE_URL
    # (already the test URL) so it migrates the right database.
    # ALEMBIC_TRANSACTION_PER_MIGRATION=1: applying the full chain to a fresh DB in
    # one transaction trips Postgres' "new enum value used before commit" rule, so
    # commit per migration here (opt-in flag; production upgrades are unaffected).
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_PROJECT_ROOT,
        env={**os.environ, "ALEMBIC_TRANSACTION_PER_MIGRATION": "1"},
        check=True,
    )
    yield


@pytest.fixture(autouse=True)
async def _truncate_between_tests():
    """Wipe every table after each test so committed rows never leak across
    tests (or into the dev DB). alembic_version is not a model table, so the
    migration state survives.
    """
    yield
    # Order is irrelevant: TRUNCATE ... CASCADE over every table resolves FK
    # dependencies itself, so use the unordered table list rather than
    # sorted_tables (which warns on the schema's mutually-dependent FK cycles).
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.tables.values())
    if not tables:
        return
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client() -> AsyncClient:
    """Pre-authenticated client — sends X-API-Key by default so the ~200
    tests written before Phase 6 auth existed don't need to know it exists.
    Tests that specifically exercise auth behavior build their own
    unauthenticated/wrong-key client instead of using this fixture.
    """
    settings = get_settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": settings.admin_api_key or ""},
    ) as async_client:
        yield async_client


@pytest.fixture
async def db() -> AsyncSession:
    """Provide an AsyncSession that always rolls back after the test.

    Rollback covers the uncommitted-work case; the session-wide
    _truncate_between_tests fixture covers anything a test (or the code under
    test) actually committed.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
