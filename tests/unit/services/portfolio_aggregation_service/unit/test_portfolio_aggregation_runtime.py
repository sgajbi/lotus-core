"""Prove supervision and configuration of the direct aggregation runtime."""

import asyncio

import pytest
from portfolio_common.runtime_settings import RuntimeConfigurationError

from src.services.portfolio_aggregation_service.app import runtime
from src.services.portfolio_aggregation_service.app.settings import (
    get_aggregation_runtime_settings,
)

pytestmark = pytest.mark.asyncio


class _FakeDispatcher:
    def __init__(self, kafka_producer):
        self.kafka_producer = kafka_producer
        self.stop_called = False
        self._stop_event = asyncio.Event()

    async def run(self):
        await self._stop_event.wait()

    def stop(self):
        self.stop_called = True
        self._stop_event.set()


class _FakeScheduler:
    def __init__(self, **kwargs):
        self.dependencies = kwargs
        self.stop_called = False
        self._stop_event = asyncio.Event()

    async def run(self):
        await self._stop_event.wait()

    def stop(self):
        self.stop_called = True
        self._stop_event.set()


class _FakeFailingScheduler(_FakeScheduler):
    async def run(self):
        raise ValueError("simulated-aggregation-scheduler-failure")


class _FakeServer:
    def __init__(self, _config):
        self.should_exit = False

    async def serve(self):
        while not self.should_exit:
            await asyncio.sleep(0.01)


@pytest.fixture
def _patch_runtime(monkeypatch):
    monkeypatch.setattr(runtime, "ensure_topics_exist", lambda *_: None)
    monkeypatch.setattr(runtime.signal, "signal", lambda *_: None)
    monkeypatch.setattr(runtime, "get_kafka_producer", lambda: object())
    monkeypatch.setattr(runtime, "OutboxDispatcher", _FakeDispatcher)
    monkeypatch.setattr(runtime, "AggregationScheduler", _FakeScheduler)
    monkeypatch.setattr(runtime.uvicorn, "Config", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime.uvicorn, "Server", _FakeServer)


async def test_runtime_gracefully_stops_scheduler_and_outbox(_patch_runtime) -> None:
    service_runtime = runtime.PortfolioAggregationRuntime()

    run_task = asyncio.create_task(service_runtime.run())
    await asyncio.sleep(0.05)
    service_runtime._shutdown_event.set()
    await asyncio.wait_for(run_task, timeout=2)

    assert service_runtime.scheduler.stop_called is True
    assert service_runtime.dispatcher.stop_called is True


async def test_runtime_ensures_only_owned_output_topics(_patch_runtime, monkeypatch) -> None:
    ensured_topics = []
    monkeypatch.setattr(
        runtime,
        "ensure_topics_exist",
        lambda topics: ensured_topics.extend(topics),
    )
    service_runtime = runtime.PortfolioAggregationRuntime()
    service_runtime._shutdown_event.set()

    await service_runtime.run()

    assert ensured_topics == [
        runtime.KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
        runtime.KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
    ]


async def test_runtime_fails_fast_on_critical_task_crash(_patch_runtime, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "AggregationScheduler", _FakeFailingScheduler)
    service_runtime = runtime.PortfolioAggregationRuntime()

    with pytest.raises(RuntimeError, match="Critical service task"):
        await asyncio.wait_for(service_runtime.run(), timeout=2)

    assert service_runtime.scheduler.stop_called is True
    assert service_runtime.dispatcher.stop_called is True


async def test_settings_read_worker_and_lease_controls(monkeypatch) -> None:
    monkeypatch.setenv("PORTFOLIO_AGGREGATION_WORKER_COUNT", "7")
    monkeypatch.setenv("AGGREGATION_JOB_LEASE_DURATION_SECONDS", "420")

    settings = get_aggregation_runtime_settings()

    assert settings.portfolio_aggregation_worker_count == 7
    assert settings.aggregation_job_lease_duration_seconds == 420


async def test_strict_settings_reject_non_positive_worker_count(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("PORTFOLIO_AGGREGATION_WORKER_COUNT", "0")

    with pytest.raises(RuntimeConfigurationError, match="PORTFOLIO_AGGREGATION_WORKER_COUNT"):
        get_aggregation_runtime_settings()
