#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

case "${1:-dev}" in
  dev)
    exec uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    ;;
  test)
    exec uv run pytest
    ;;
  migrate)
    exec uv run alembic upgrade head
    ;;
  lint)
    exec uv run ruff check app tests
    ;;
  format)
    exec uv run ruff format app tests
    ;;
  *)
    echo "Usage: $0 {dev|test|migrate|lint|format}"
    exit 1
    ;;
esac
