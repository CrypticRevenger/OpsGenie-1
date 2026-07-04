FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
COPY app ./app

RUN uv sync --frozen --no-dev

FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app/.venv /app/.venv
COPY pyproject.toml uv.lock ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

# Apply migrations before serving, then hand PID 1 to uvicorn via exec so it
# receives signals. `&&` makes a failed migration abort startup (fail fast)
# rather than serving against an out-of-date schema.
# NOTE: for a single-instance pilot this is correct. If you scale to multiple
# replicas, move `alembic upgrade head` into a separate one-shot job so N
# replicas don't race to migrate on boot.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
