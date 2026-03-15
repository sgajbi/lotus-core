# syntax=docker/dockerfile:1.7
# src/services/calculators/position_valuation_calculator/Dockerfile

# Stage 1: Base image setup
FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# --- FIX: Add build-essential and libpq-dev for compiling dependencies ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && chown -R appuser:appuser /opt/venv

WORKDIR /app

# Stage 2: Builder
FROM python-base as builder

# Shared libs first for caching
COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/src/libs/portfolio-common

# Copy service and install
COPY src/services/calculators/position_valuation_calculator/pyproject.toml /app/src/services/calculators/position_valuation_calculator/pyproject.toml
COPY src/services/calculators/position_valuation_calculator/app /app/src/services/calculators/position_valuation_calculator/app
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /app/src/services/calculators/position_valuation_calculator

# Stage 3: Final
FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/calculators/position_valuation_calculator/app /app/app

USER appuser
EXPOSE 8084
CMD ["python", "-m", "app.main"]
