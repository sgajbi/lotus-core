# syntax=docker/dockerfile:1.7
# src/services/pipeline_orchestrator_service/Dockerfile

ARG PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:97b0eafb29f5ebfba254be840115b2f3bc24ff6ff3de9b905e04b74ee7227ba6
ARG LOTUS_GIT_COMMIT_SHA=unknown
ARG LOTUS_GIT_BRANCH=unknown
ARG LOTUS_BUILD_TIMESTAMP=unknown
ARG LOTUS_REPO_URL=unknown
ARG LOTUS_IMAGE_VERSION=unknown
ARG LOTUS_IMAGE_DIGEST=unknown
ARG LOTUS_CI_RUN_ID=unknown

FROM ${PYTHON_IMAGE} AS runtime-base

ARG LOTUS_GIT_COMMIT_SHA
ARG LOTUS_GIT_BRANCH
ARG LOTUS_BUILD_TIMESTAMP
ARG LOTUS_REPO_URL
ARG LOTUS_IMAGE_VERSION
ARG LOTUS_IMAGE_DIGEST
ARG LOTUS_CI_RUN_ID

LABEL org.opencontainers.image.revision=${LOTUS_GIT_COMMIT_SHA} \
    org.opencontainers.image.ref.name=${LOTUS_GIT_BRANCH} \
    org.opencontainers.image.created=${LOTUS_BUILD_TIMESTAMP} \
    org.opencontainers.image.source=${LOTUS_REPO_URL} \
    org.opencontainers.image.version=${LOTUS_IMAGE_VERSION} \
    org.opencontainers.image.digest=${LOTUS_IMAGE_DIGEST} \
    org.opencontainers.image.ci.run_id=${LOTUS_CI_RUN_ID}

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CONSTRAINT=/app/requirements/shared-runtime.lock.txt \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    LOTUS_GIT_COMMIT_SHA=${LOTUS_GIT_COMMIT_SHA} \
    LOTUS_GIT_BRANCH=${LOTUS_GIT_BRANCH} \
    LOTUS_BUILD_TIMESTAMP=${LOTUS_BUILD_TIMESTAMP} \
    LOTUS_REPO_URL=${LOTUS_REPO_URL} \
    LOTUS_IMAGE_VERSION=${LOTUS_IMAGE_VERSION} \
    LOTUS_IMAGE_DIGEST=${LOTUS_IMAGE_DIGEST} \
    LOTUS_CI_RUN_ID=${LOTUS_CI_RUN_ID}

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
COPY src/services/pipeline_orchestrator_service/pyproject.toml /build/src/services/pipeline_orchestrator_service/pyproject.toml
COPY src/services/pipeline_orchestrator_service/app /build/src/services/pipeline_orchestrator_service/app

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip wheel --wheel-dir /wheels \
    /build/src/libs/portfolio-common \
    /build/src/services/pipeline_orchestrator_service

FROM runtime-base AS final

COPY --from=wheel-builder /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --no-index --find-links=/wheels /wheels/*.whl && \
    rm -rf /wheels && \
    chown -R appuser:appuser /opt/venv

USER appuser
EXPOSE 8086
CMD ["python", "-m", "app.main"]
