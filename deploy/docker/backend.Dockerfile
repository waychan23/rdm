# syntax=docker/dockerfile:1

# Backend image: API/MCP/CLI only. The Web UI is built by web.Dockerfile.
ARG PYTHON_IMAGE=python:3.13-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.8.17

FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY src ./src

# The PostgreSQL driver is always installed so the optional compose `db`
# profile works without rebuilding the image.
RUN uv sync --frozen --no-dev --no-editable --extra postgres

RUN useradd --create-home --uid 10001 rdm \
    && mkdir -p /data \
    && chown -R rdm:rdm /data /app
USER rdm

ENV RDM_DATA_DIR=/data \
    RDM_HOST=0.0.0.0 \
    RDM_PORT=8765

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8765/api/healthz || exit 1

CMD ["rdm", "serve", "--host", "0.0.0.0", "--port", "8765", "--data-dir", "/data"]
