# syntax=docker/dockerfile:1.7
# src/services/query_control_plane_service/Dockerfile

FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
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

COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/src/libs/portfolio-common
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install python-dateutil

COPY src/services/query_control_plane_service/pyproject.toml /app/src/services/query_control_plane_service/pyproject.toml
COPY src/services/query_control_plane_service/app /app/src/services/query_control_plane_service/app
COPY src/services/query_service/app /app/src/services/query_service/app
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /app/src/services/query_control_plane_service

FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/query_control_plane_service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/src/services/query_service/app /app/src/services/query_service/app
COPY --from=builder --chown=appuser:appuser /app/src/libs /app/src/libs

USER appuser
EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
