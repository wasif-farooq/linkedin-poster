# syntax=docker/dockerfile:1
#
# One image: the FastAPI app serving the API and the built React UI on :8000.
# State (conversations, post history, LinkedIn token, caches, your voice guide) lives in
# /app/data — mount a volume there or it is lost on every redeploy.

# ── 1. frontend ────────────────────────────────────────────────────────────────
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ── 2. app ─────────────────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first: this layer only rebuilds when the lockfile changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY config ./config
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./frontend/dist

# Unprivileged, and the only writable place is the data volume.
RUN useradd --uid 10001 --no-create-home app && mkdir -p /app/data && chown app /app/data
USER app

ENV PATH=/app/.venv/bin:$PATH \
    VOICE_PATH=/app/data/voice.md
VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# Seed the editable voice guide into the volume on first start, then run the API.
# One process on purpose: runs are serialized in-process (shared LLM/search budgets).
CMD ["sh", "-c", "[ -f /app/data/voice.md ] || cp /app/config/voice.md /app/data/voice.md; exec linkedin-poster serve --host 0.0.0.0 --port 8000"]
