# OpsGenie Documentation

Project documentation lives here. Product requirements and technical design are
maintained privately and are not part of this repository.

## Contents

- [Getting Started](getting-started.md) — local setup, environment, and common commands
- [API Reference](api.md) — every route, auth model, and error shape

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
