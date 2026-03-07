# Stage 1: Base image setup
FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
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

ENV PYTHONPATH="/app/src/libs/portfolio-common:/app/src/services/pipeline_orchestrator_service"

COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN pip install -e /app/src/libs/portfolio-common

COPY src/services/pipeline_orchestrator_service/pyproject.toml /app/src/services/pipeline_orchestrator_service/pyproject.toml
COPY src/services/pipeline_orchestrator_service/app /app/src/services/pipeline_orchestrator_service/app
RUN pip install /app/src/services/pipeline_orchestrator_service

# Stage 3: Final production stage
FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/pipeline_orchestrator_service/app /app/app

USER appuser

EXPOSE 8086

CMD ["python", "-m", "app.main"]
