import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from portfolio_common import worker_runtime


@pytest.mark.asyncio
async def test_run_kafka_worker_runtime_composes_consumers_dispatcher_and_health(
    monkeypatch,
) -> None:
    consumer = MagicMock(topic="transactions.persisted")
    consumer.run = AsyncMock()
    dispatcher = MagicMock()
    dispatcher.run = AsyncMock()
    dispatcher.stop = MagicMock()
    server = MagicMock()
    server.serve = AsyncMock()
    server_config_factory = MagicMock(return_value="server-config")
    server_factory = MagicMock(return_value=server)
    ensure_topics = MagicMock()
    signal_module = MagicMock(SIGINT=2, SIGTERM=15)
    logger = MagicMock(spec=logging.Logger)
    tasks: list[asyncio.Task] = []

    async def _wait_for_tasks(**kwargs):
        await asyncio.gather(*kwargs["tasks"])
        return None

    shutdown = AsyncMock()
    monkeypatch.setattr(worker_runtime, "wait_for_shutdown_or_task_failure", _wait_for_tasks)
    monkeypatch.setattr(worker_runtime, "shutdown_runtime_components", shutdown)

    await worker_runtime.run_kafka_worker_runtime(
        consumers=[consumer],
        dispatcher=dispatcher,
        web_app="worker-app",
        web_port=8083,
        readiness_service_name="transaction_worker",
        shutdown_event=asyncio.Event(),
        signal_handler=MagicMock(),
        tasks=tasks,
        logger=logger,
        ensure_topics=ensure_topics,
        signal_module=signal_module,
        server_config_factory=server_config_factory,
        server_factory=server_factory,
    )

    ensure_topics.assert_called_once_with(["transactions.persisted"])
    assert signal_module.signal.call_count == 2
    server_config_factory.assert_called_once_with(
        "worker-app",
        host="0.0.0.0",
        port=8083,
        log_config=None,
    )
    server_factory.assert_called_once_with("server-config")
    assert len(tasks) == 3
    consumer.run.assert_awaited_once()
    dispatcher.run.assert_awaited_once()
    server.serve.assert_awaited_once()
    shutdown.assert_awaited_once()


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
