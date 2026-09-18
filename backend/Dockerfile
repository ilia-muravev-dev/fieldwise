# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
# libglib is needed by opencv-python-headless; nothing else from the OS.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/
WORKDIR /app

FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

FROM deps AS runtime
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
# OCR and embedding models are fetched on first use into these caches (mounted volumes in compose).
ENV HF_HOME=/models/hf FASTEMBED_CACHE_PATH=/models/fastembed
EXPOSE 8000
CMD ["uvicorn", "fieldwise.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
