# syntax=docker/dockerfile:1
# Workbench API (FastAPI). Built by .github/workflows/build-images.yml.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DO_NOT_TRACK=true \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Poppler for pdf2image, libmagic for unstructured
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        libgl1 \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /bin/uv

WORKDIR /app

# Dependencies first, from the lock, so code changes reuse this layer
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY . .

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin workbench
USER 10001

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.workbench.main:app", "--host", "0.0.0.0", "--port", "8000"]
