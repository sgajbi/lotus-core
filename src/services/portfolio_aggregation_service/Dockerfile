# src/services/portfolio_aggregation_service/Dockerfile

FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && chown -R appuser:appuser /opt/venv

WORKDIR /app

FROM python-base as builder

COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN pip install -e /app/src/libs/portfolio-common

COPY src/services/portfolio_aggregation_service/pyproject.toml /app/src/services/portfolio_aggregation_service/pyproject.toml
COPY src/services/portfolio_aggregation_service/app /app/src/services/portfolio_aggregation_service/app
RUN pip install /app/src/services/portfolio_aggregation_service

FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/portfolio_aggregation_service/app /app/app

USER appuser
EXPOSE 8088
CMD ["python", "-m", "app.main"]
