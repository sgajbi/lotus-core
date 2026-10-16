"""Stop/idle ownership and unexpected failure propagate to native supervision."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from portfolio_common.runtime_settings import (
    FinancialSourceCutWorkerSettings,
    financial_source_cut_worker_settings,
)

from src.services.persistence_service.app.financial_source_cut_worker import (
    FinancialSourceCutWorker,
    build_financial_source_cut_workers,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_idle_worker_stops_promptly_and_closes_client():
    processor = SimpleNamespace(
        step=AsyncMock(return_value=False), captures=SimpleNamespace(close=AsyncMock())
    )
    worker = FinancialSourceCutWorker(processor, idle_seconds=10)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)
    worker.stop()
    await asyncio.wait_for(task, 1)
    processor.captures.close.assert_awaited_once()


async def test_unexpected_repository_failure_is_not_hidden_by_poll_loop():
    processor = SimpleNamespace(
        step=AsyncMock(side_effect=RuntimeError("lost repository")),
        captures=SimpleNamespace(close=AsyncMock()),
    )
    worker = FinancialSourceCutWorker(processor)
    with pytest.raises(RuntimeError, match="lost repository"):
        await worker.run()
    processor.captures.close.assert_awaited_once()


async def test_factory_uses_bounded_concurrency_independent_claim_state_and_no_initial_sql():
    sessions = Mock()
    workers = build_financial_source_cut_workers(
        sessions, settings=FinancialSourceCutWorkerSettings(2, 30, 5, 500)
    )
    assert len(workers) == 2
    assert workers[0].processor.work is not workers[1].processor.work
    assert workers[0].processor.work.sessions is sessions
    assert workers[1].processor.captures.sessions is sessions
    assert all(worker.idle_seconds == 0.5 for worker in workers)
    sessions.assert_not_called()


async def test_strict_worker_runtime_configuration_refuses_unbounded_concurrency(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("LOTUS_FINANCIAL_SOURCE_CUT_WORKERS", "999")
    with pytest.raises(ValueError):
        financial_source_cut_worker_settings()
