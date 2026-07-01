# OpsGenie Documentation

Project documentation lives here. Product requirements and technical design remain in the repository root [`SPEC.md`](../SPEC.md).

## Contents

- [Getting Started](getting-started.md) — local setup, environment, and common commands

## Architecture (Phase 0)

```
FastAPI (app/)
    ├── core/       config, logging, exceptions
    ├── api/        HTTP routes
    └── db/         SQLAlchemy async session + Alembic
         ↓
PostgreSQL 16
```

Phase 1 will add the full database schema and initial Alembic migration.
