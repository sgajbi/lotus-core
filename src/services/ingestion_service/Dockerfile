# syntax=docker/dockerfile:1.7
# src/services/ingestion_service/Dockerfile

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

FROM ${PYTHON_IMAGE} AS runtime-base

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CONSTRAINT=/app/constraints/shared-build-constraints.txt \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser && \
    python -m venv /opt/venv && \
    chown -R appuser:appuser /opt/venv

WORKDIR /app
COPY constraints/shared-build-constraints.txt /app/constraints/shared-build-constraints.txt

FROM ${PYTHON_IMAGE} AS wheel-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CONSTRAINT=/build/constraints/shared-build-constraints.txt \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY constraints/shared-build-constraints.txt /build/constraints/shared-build-constraints.txt
COPY src/libs/portfolio-common /build/src/libs/portfolio-common
COPY src/services/ingestion_service/pyproject.toml /build/src/services/ingestion_service/pyproject.toml
COPY src/services/ingestion_service/app /build/src/services/ingestion_service/app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels \
    /build/src/libs/portfolio-common \
    /build/src/services/ingestion_service

FROM runtime-base AS final

COPY --from=wheel-builder /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-index --find-links=/wheels /wheels/*.whl && \
    rm -rf /wheels && \
    chown -R appuser:appuser /opt/venv

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
