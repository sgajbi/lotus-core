# syntax=docker/dockerfile:1.7
# src/services/calculators/cost_calculator_service/Dockerfile

FROM python:3.11-slim-bookworm as python-base

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CONSTRAINT=/app/constraints/shared-build-constraints.txt \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && chown -R appuser:appuser /opt/venv

WORKDIR /app
COPY constraints/shared-build-constraints.txt /app/constraints/shared-build-constraints.txt

FROM python-base as builder

# 1. Copy local shared library source first
COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/

# 2. Copy service app code
COPY src/services/calculators/cost_calculator_service/pyproject.toml /app/src/services/calculators/cost_calculator_service/pyproject.toml
COPY src/services/calculators/cost_calculator_service/app /app/src/services/calculators/cost_calculator_service/app

# 3. Install all packages
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /app/src/libs/portfolio-common
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /app/src/services/calculators/cost_calculator_service


FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/calculators/cost_calculator_service/app /app/app

USER appuser
EXPOSE 8083
CMD ["python", "-m", "app.main"]
