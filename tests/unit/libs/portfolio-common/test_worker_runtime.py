import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
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
    web_app = object()

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
    logger.info.assert_any_call("Prometheus metrics exposed at /metrics")
    logger.info.assert_any_call("%s has shut down.", "Example Worker")


@pytest.mark.asyncio
async def test_run_instrumented_worker_service_reraises_critical_runtime_errors(monkeypatch):
    instrumentator = MagicMock()
    instrumentator.instrument.return_value = instrumentator
    instrumentator.expose.return_value = instrumentator
    monkeypatch.setattr(worker_runtime, "Instrumentator", MagicMock(return_value=instrumentator))

    manager = MagicMock()
    manager.run = AsyncMock(side_effect=RuntimeError("boom"))
    logger = MagicMock(spec=logging.Logger)

    with pytest.raises(RuntimeError, match="boom"):
        await worker_runtime.run_instrumented_worker_service(
            service_name="Example Worker",
            logger=logger,
            manager=manager,
            web_app=object(),
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

    with pytest.raises(RuntimeError, match="metrics setup failed"):
        await worker_runtime.run_instrumented_worker_service(
            service_name="Example Worker",
            logger=logger,
            manager=manager,
            web_app=object(),
        )

    manager.run.assert_not_awaited()
    logger.critical.assert_called_once_with(
        "%s encountered a critical error",
        "Example Worker",
        exc_info=True,
    )
    logger.info.assert_any_call("%s has shut down.", "Example Worker")
