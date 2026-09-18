# fieldwise task runner — `just` lists the recipes.

default:
    @just --list

# Start the infrastructure services (Postgres with pgvector, Redis)
up:
    docker compose up -d --wait db redis

# Start everything: database, redis, migrations, API, worker (and the web app when present)
app:
    docker compose --profile app up -d --build --wait

# The whole stack with the fake model provider (what the e2e tests run against)
app-e2e:
    docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile app up -d --build --wait

# Stop everything
down:
    docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile app down

# Lint, types and tests for the backend
backend-check:
    cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest

# Fix what ruff can fix and format
backend-fix:
    cd backend && uv run ruff check --fix . && uv run ruff format .

# Regenerate the API contract and the typed web client built from it
openapi:
    cd backend && uv run fieldwise openapi ../openapi.json
    cd web && pnpm gen:api

# Fail when openapi.json is stale (CI runs this)
openapi-check:
    cd backend && uv run fieldwise openapi /tmp/fieldwise-openapi.json >/dev/null && diff -q /tmp/fieldwise-openapi.json ../openapi.json

# Lint, types, tests and build for the web app
web-check:
    cd web && pnpm lint && pnpm typecheck && pnpm test && pnpm build

# Regenerate the typed web client from openapi.json
web-client:
    cd web && pnpm gen:api

# Rebuild the gate bundle from the local database (after re-ingesting or changing OCR)
gate-build:
    cd backend && uv run fieldwise gate build --limit 20

# Everything CI runs
check: backend-check openapi-check web-check

# Run the web app locally (proxies /api to :8000)
web:
    cd web && pnpm dev

# Browser smoke test against the running stack (`just app-e2e` first)
e2e:
    cd web && pnpm e2e

# Run the API locally with reload
api:
    cd backend && uv run uvicorn fieldwise.api.app:app --reload --port 8000

# Run the worker locally
worker:
    cd backend && uv run celery -A fieldwise.worker.app:celery_app worker --loglevel=info --concurrency=2
