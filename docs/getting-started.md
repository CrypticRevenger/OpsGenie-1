# Getting Started

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- PostgreSQL 16 (local, Docker, or Neon)

Optional:

- Docker Desktop (for `docker compose`)
- `make` (Git Bash, WSL, or `choco install make`)

## Setup

```powershell
# From the project root
uv sync --all-extras

# Environment is already copied to .env — edit DATABASE_URL if needed
notepad .env

# Install pre-commit hooks (optional but recommended)
uv run pre-commit install
```

## Run the API

```powershell
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
```

## Common Commands

| Task | Command |
|------|---------|
| Install deps | `uv sync --all-extras` |
| Run server | `make dev` or `uv run uvicorn app.main:app --reload` |
| Run tests | `make test` |
| Lint | `make lint` |
| Format | `make format` |
| Migrations | `make migrate` |
| Docker stack | `make docker-up` |

## PostgreSQL

Local default from `.env`:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/opsgenie
```

For Neon or other cloud providers, append `?ssl=require` when needed.

Create the database locally:

```powershell
docker compose -f docker/docker-compose.yml up -d postgres
```

Or with `psql`:

```sql
CREATE DATABASE opsgenie;
```

## Next Steps

Phase 1 adds all ORM models and the initial Alembic migration defined in [`SPEC.md`](../SPEC.md) (TDD schema section).
