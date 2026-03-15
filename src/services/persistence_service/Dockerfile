# syntax=docker/dockerfile:1.7
# src/services/persistence_service/Dockerfile

# Stage 1: Base image setup
FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && \
    chown -R appuser:appuser /opt/venv

WORKDIR /app

# Stage 2: Builder stage
FROM python-base as builder

ENV PYTHONPATH="/app/src/libs/portfolio-common:/app/src/services/persistence_service"

COPY ./src/libs/portfolio-common /app/src/libs/portfolio-common
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/src/libs/portfolio-common

COPY ./src/services/persistence_service/pyproject.toml /app/src/services/persistence_service/pyproject.toml
COPY ./src/services/persistence_service/app /app/src/services/persistence_service/app
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /app/src/services/persistence_service

COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY tools /app/tools

# Stage 3: Final production stage
FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/persistence_service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/src/libs /app/src/libs
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /app/tools /app/tools

USER appuser

EXPOSE 8080

CMD ["python", "-m", "app.main"]
