import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from portfolio_common import worker_runtime


@pytest.mark.asyncio
async def test_run_instrumented_worker_service_instruments_and_runs(monkeypatch):
    instrumentator = MagicMock()
    instrumentator.instrument.return_value = instrumentator
    instrumentator.expose.return_value = instrumentator
    instrumentator_cls = MagicMock(return_value=instrumentator)
    monkeypatch.setattr(worker_runtime, "Instrumentator", instrumentator_cls)

    manager = MagicMock()
    manager.run = AsyncMock()
    logger = MagicMock(spec=logging.Logger)
    web_app = FastAPI()

    await worker_runtime.run_instrumented_worker_service(
        service_name="Example Worker",
        logger=logger,
        manager=manager,
        web_app=web_app,
    )

    instrumentator_cls.assert_called_once_with()
    instrumentator.instrument.assert_called_once_with(web_app)
    instrumentator.expose.assert_called_once_with(web_app)
    manager.run.assert_awaited_once()
    logger.info.assert_any_call("%s starting up...", "Example Worker")
    logger.info.assert_any_call(
        "Prometheus metrics exposed at /metrics",
        extra={"metrics_access_mode": "internal_open"},
    )
    logger.info.assert_any_call("%s has shut down.", "Example Worker")


@pytest.mark.asyncio
async def test_run_instrumented_worker_service_skips_existing_metrics_route(monkeypatch):
    instrumentator_cls = MagicMock()
    monkeypatch.setattr(worker_runtime, "Instrumentator", instrumentator_cls)

    manager = MagicMock()
    manager.run = AsyncMock()
    logger = MagicMock(spec=logging.Logger)
    metrics_route = MagicMock()
    metrics_route.path = "/metrics"
    web_app = FastAPI()
    web_app.router.routes.append(metrics_route)

    await worker_runtime.run_instrumented_worker_service(
        service_name="Example Worker",
        logger=logger,
        manager=manager,
        web_app=web_app,
    )

    instrumentator_cls.assert_not_called()
    manager.run.assert_awaited_once()
    logger.info.assert_any_call(
        "Prometheus metrics already exposed at /metrics",
        extra={"metrics_access_mode": "internal_open"},
    )
    logger.info.assert_any_call("%s has shut down.", "Example Worker")


@pytest.mark.asyncio
async def test_worker_runtime_metrics_endpoint_uses_shared_token_policy():
    manager = MagicMock()
    manager.run = AsyncMock()
    logger = MagicMock(spec=logging.Logger)
    web_app = FastAPI()

    await worker_runtime.run_instrumented_worker_service(
        service_name="Example Worker",
        logger=logger,
        manager=manager,
        web_app=web_app,
        metrics_access_token="scrape-secret",
    )

    client = TestClient(web_app)
    client.get("/not-found")
    denied_response = client.get("/metrics")
    allowed_response = client.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})

    assert denied_response.status_code == 403
    assert denied_response.json()["detail"]["code"] == "METRICS_ACCESS_DENIED"
    assert allowed_response.status_code == 200
    assert "http_request_latency_seconds" in allowed_response.text


@pytest.mark.asyncio
async def test_worker_runtime_existing_metrics_route_still_uses_shared_token_policy(monkeypatch):
    instrumentator_cls = MagicMock()
    monkeypatch.setattr(worker_runtime, "Instrumentator", instrumentator_cls)

    manager = MagicMock()
    manager.run = AsyncMock()
    logger = MagicMock(spec=logging.Logger)
    web_app = FastAPI()

    @web_app.get("/metrics")
    def existing_metrics_route():
        return "worker metrics"

    await worker_runtime.run_instrumented_worker_service(
        service_name="Example Worker",
        logger=logger,
        manager=manager,
        web_app=web_app,
        metrics_access_token="scrape-secret",
    )

    client = TestClient(web_app)
    denied_response = client.get("/metrics")
    allowed_response = client.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})

    instrumentator_cls.assert_not_called()
    assert denied_response.status_code == 403
    assert denied_response.json()["detail"]["code"] == "METRICS_ACCESS_DENIED"
    assert allowed_response.status_code == 200


@pytest.mark.asyncio
async def test_run_instrumented_worker_service_reraises_critical_runtime_errors(monkeypatch):
    instrumentator = MagicMock()
    instrumentator.instrument.return_value = instrumentator
    instrumentator.expose.return_value = instrumentator
    monkeypatch.setattr(worker_runtime, "Instrumentator", MagicMock(return_value=instrumentator))

    manager = MagicMock()
    manager.run = AsyncMock(side_effect=RuntimeError("boom"))
    logger = MagicMock(spec=logging.Logger)
    web_app = FastAPI()

    with pytest.raises(RuntimeError, match="boom"):
        await worker_runtime.run_instrumented_worker_service(
            service_name="Example Worker",
            logger=logger,
            manager=manager,
            web_app=web_app,
        )

    logger.critical.assert_called_once_with(
        "%s encountered a critical error",
        "Example Worker",
        exc_info=True,
    )
    logger.info.assert_any_call("%s has shut down.", "Example Worker")


@pytest.mark.asyncio
async def test_run_instrumented_worker_service_logs_startup_instrumentation_failure(monkeypatch):
    instrumentator = MagicMock()
    instrumentator.instrument.side_effect = RuntimeError("metrics setup failed")
    monkeypatch.setattr(worker_runtime, "Instrumentator", MagicMock(return_value=instrumentator))

    manager = MagicMock()
    manager.run = AsyncMock()
    logger = MagicMock(spec=logging.Logger)
    web_app = FastAPI()

    with pytest.raises(RuntimeError, match="metrics setup failed"):
        await worker_runtime.run_instrumented_worker_service(
            service_name="Example Worker",
            logger=logger,
            manager=manager,
            web_app=web_app,
        )

    manager.run.assert_not_awaited()
    logger.critical.assert_called_once_with(
        "%s encountered a critical error",
        "Example Worker",
        exc_info=True,
    )
    logger.info.assert_any_call("%s has shut down.", "Example Worker")
