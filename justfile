# fieldwise task runner — `just` lists the recipes.

default:
    @just --list

# Start the infrastructure services (Postgres with pgvector, Redis)
up:
    docker compose up -d --wait db redis

# Stop everything
down:
    docker compose down

# Lint, types and tests for the backend
backend-check:
    cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest

# Fix what ruff can fix and format
backend-fix:
    cd backend && uv run ruff check --fix . && uv run ruff format .

# Everything CI runs
check: backend-check

# Run the API locally with reload
api:
    cd backend && uv run uvicorn fieldwise.api.app:app --reload --port 8000
