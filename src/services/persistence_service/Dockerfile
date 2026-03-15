# syntax=docker/dockerfile:1.7
# src/services/persistence_service/Dockerfile

ARG PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:97b0eafb29f5ebfba254be840115b2f3bc24ff6ff3de9b905e04b74ee7227ba6

FROM ${PYTHON_IMAGE} AS runtime-base

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CONSTRAINT=/app/requirements/shared-runtime.lock.txt \
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
COPY requirements/shared-runtime.lock.txt /app/requirements/shared-runtime.lock.txt

FROM ${PYTHON_IMAGE} AS wheel-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CONSTRAINT=/build/requirements/shared-runtime.lock.txt \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements/shared-runtime.lock.txt /build/requirements/shared-runtime.lock.txt
COPY src/libs/portfolio-common /build/src/libs/portfolio-common
COPY src/services/persistence_service/pyproject.toml /build/src/services/persistence_service/pyproject.toml
COPY src/services/persistence_service/app /build/src/services/persistence_service/app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels \
    /build/src/libs/portfolio-common \
    /build/src/services/persistence_service

FROM runtime-base AS final

COPY --from=wheel-builder /wheels /wheels
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY tools/kafka_setup.py /app/tools/kafka_setup.py
COPY tools/demo_data_pack.py /app/tools/demo_data_pack.py
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-index --find-links=/wheels /wheels/*.whl && \
    rm -rf /wheels && \
    chown -R appuser:appuser /opt/venv /app

USER appuser
EXPOSE 8080
CMD ["python", "-m", "app.main"]
