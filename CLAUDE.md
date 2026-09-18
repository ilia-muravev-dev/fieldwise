# fieldwise — notes for coding agents

Monorepo: `backend/` (Python 3.12, uv, FastAPI, SQLAlchemy 2 sync + psycopg 3, Celery, Typer CLI)
and `web/` (Next.js). Postgres with pgvector and Redis run from `docker-compose.yml`.

## Commands
- `just up` — Postgres + Redis; `just app` — the whole stack in Docker (migrate, API :8000, worker);
  `just check` — everything CI runs; `just backend-fix` — ruff fixes + format; `just openapi` — regenerate the contract
- `cd backend && uv run fieldwise --help` — the CLI: `db`, `schemas`, `ingest`, `ocr`, `extract`, `eval`
- `uv run fieldwise eval run --prompt v1 --limit 20 --cassette record` — measure; `eval compare a b` — the README table
- Tests: `uv run pytest` (unit) — integration tests need Docker and are marked `integration`
- Web: `just web` (dev server on :3000, proxies `/api` to :8000), `just web-check`; the typed client in
  `web/src/lib/api/schema.d.ts` is generated from `openapi.json` — never edit it by hand

## Rules of the codebase
- Evals first: any change to a prompt, the schema compiler or a matcher must be re-measured, and the
  report committed under `docs/evals/`. Numbers in the README come only from those reports.
- Never spend API money silently: the eval CLI prints a cost estimate and asks unless `--yes`; CI
  runs on replayed cassettes only.
- Few-shot examples come from labelled non-test documents only — the test split is for measuring.
- Infra failures (timeouts, rate limits, truncation) are recorded in the error sidecar and are never
  scored as wrong answers.
- Warnings are errors in pytest; mypy is strict; keep functions typed.
- The Anthropic SDK is called only through `fieldwise.extraction.provider` so that the fake and
  cassette providers stay drop-in replacements.

## Review checklist for PRs
- Does a test prove the behaviour (matchers, schema compiler, mapper), or only that code ran?
- Any change to `openapi.json` is a contract change: regenerate the web client and mention it.
- Migrations: additive, reversible, and checked against a clean database in CI.
