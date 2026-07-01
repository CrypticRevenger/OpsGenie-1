.PHONY: install dev test lint format migrate docker-up docker-down pre-commit

install:
	uv sync --all-extras

dev:
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check app tests

format:
	uv run ruff format app tests

migrate:
	uv run alembic upgrade head

docker-up:
	docker compose -f docker/docker-compose.yml up -d --build

docker-down:
	docker compose -f docker/docker-compose.yml down

pre-commit:
	uv run pre-commit install
	uv run pre-commit run --all-files
