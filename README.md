# OpsGenie

WhatsApp-first daily financial operating assistant for B2B distributors.

OpsGenie converts existing business records (Tally/Vyapar exports) into daily operational decisions delivered through WhatsApp — with zero learning curve for the distributor.

## Status

**Phases 1–9 complete** — full backend from schema through a working WhatsApp integration:

- Admin CRUD (company / dealer / supplier) with shared-key auth and pagination
- CSV/Excel import with idempotent, FIFO payment allocation
- Invoice & payment read APIs with computed outstanding balances
- `BusinessSnapshotService` + `RecommendationEngine` (pure Python, no LLM)
- Morning briefing narration via a pluggable multi-provider LLM chain with automatic failover
- Inbound WhatsApp webhook, numbered query menu, and stateful invoice due-date follow-up conversations

Deterministic business engine validated against real distributor data; 295 tests passing.

## Quick Start

```powershell
# Install dependencies
uv sync --all-extras

# Start PostgreSQL (Docker)
docker compose -f docker/docker-compose.yml up -d postgres

# Run API
make dev
# or: uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Health check
curl http://127.0.0.1:8000/health
```

## Project Structure

```
app/
  core/          Settings, logging, exception handlers
  api/           HTTP routes
  db/            SQLAlchemy async engine and session
  main.py        FastAPI application factory
alembic/         Database migrations
tests/           Pytest suite
scripts/         Dev helper scripts (PowerShell + Bash)
docker/          Dockerfile and docker-compose
```

## Commands

| Make target | Description |
|-------------|-------------|
| `make install` | Install all dependencies with uv |
| `make dev` | Run API with hot reload |
| `make test` | Run pytest |
| `make lint` | Ruff lint |
| `make format` | Ruff format |
| `make migrate` | Apply Alembic migrations |
| `make docker-up` | Start Postgres + API in Docker |
| `make pre-commit` | Install and run pre-commit hooks |

Windows without `make`: use `scripts/dev.ps1` (`.\scripts\dev.ps1 dev`).

## Environment

Copy or edit `.env` (`.env.example` is the template):

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/opsgenie
```

For Neon/cloud Postgres, append `?ssl=require` when required.

## Engineering Principles

From the product spec — these never change:

- LLMs never own business state, calculate money, or decide recommendations
- Every briefing number traces to a real database record
- All business rules live in deterministic Python code

## License

Proprietary — all rights reserved. See [LICENSE](LICENSE).
