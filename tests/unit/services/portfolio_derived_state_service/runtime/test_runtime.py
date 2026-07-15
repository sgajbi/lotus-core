"""Prove supervision and configuration of the unified derived-state runtime."""

import asyncio
from collections.abc import Callable

import pytest
from portfolio_common.runtime_settings import RuntimeConfigurationError

from src.services.portfolio_derived_state_service.app import runtime
from src.services.portfolio_derived_state_service.app.settings import (
    get_aggregation_runtime_settings,
)

pytestmark = pytest.mark.asyncio


class _FakeDispatcher:
    instances: list["_FakeDispatcher"] = []

    def __init__(self, kafka_producer: object) -> None:
        self.kafka_producer = kafka_producer
        self.stop_called = False
        self._stop_event = asyncio.Event()
        self.instances.append(self)

    async def run(self) -> None:
        await self._stop_event.wait()

    def stop(self) -> None:
        self.stop_called = True
        self._stop_event.set()


class _FakeScheduler:
    def __init__(self, **dependencies: object) -> None:
        self.dependencies = dependencies
        self.stop_called = False
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        await self._stop_event.wait()

    def stop(self) -> None:
        self.stop_called = True
        self._stop_event.set()


class _FakeFailingScheduler(_FakeScheduler):
    async def run(self) -> None:
        raise ValueError("simulated-aggregation-scheduler-failure")


class _FakeConsumer:
    def __init__(self, **dependencies: object) -> None:
        self.dependencies = dependencies
        self.topic = str(dependencies["topic"])
        self.shutdown_called = False
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        await self._stop_event.wait()

    def shutdown(self) -> None:
        self.shutdown_called = True
        self._stop_event.set()


class _FakeFailingConsumer(_FakeConsumer):
    async def run(self) -> None:
        raise ValueError("simulated-position-consumer-failure")


class _FakeServer:
    def __init__(self, _config: object) -> None:
        self.should_exit = False

    async def serve(self) -> None:
        while not self.should_exit:
            await asyncio.sleep(0.01)


@pytest.fixture(autouse=True)
def _reset_fakes() -> None:
    _FakeDispatcher.instances.clear()


@pytest.fixture
def patch_runtime(monkeypatch) -> Callable[..., None]:
    monkeypatch.setattr(runtime, "ensure_topics_exist", lambda *_: None)
    monkeypatch.setattr(runtime.signal, "signal", lambda *_: None)
    monkeypatch.setattr(runtime, "get_kafka_producer", lambda: object())
    monkeypatch.setattr(runtime, "OutboxDispatcher", _FakeDispatcher)
    monkeypatch.setattr(runtime.uvicorn, "Config", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime.uvicorn, "Server", _FakeServer)

    def apply(
        *,
        consumer: type[_FakeConsumer] = _FakeConsumer,
        scheduler: type[_FakeScheduler] = _FakeScheduler,
    ) -> None:
        monkeypatch.setattr(runtime, "PositionTimeseriesConsumer", consumer)
        monkeypatch.setattr(runtime, "AggregationScheduler", scheduler)

    apply()
    return apply


async def test_runtime_composes_one_dispatcher_and_preserves_position_offsets(
    patch_runtime: Callable[..., None],
) -> None:
    service_runtime = runtime.PortfolioDerivedStateRuntime()

    assert len(service_runtime.consumers) == 1
    assert service_runtime.consumers[0].dependencies["group_id"] == (
        runtime.POSITION_TIMESERIES_CONSUMER_GROUP
    )
    assert runtime.POSITION_TIMESERIES_CONSUMER_GROUP == "timeseries_generator_group_positions"
    assert len(_FakeDispatcher.instances) == 1
    assert str(service_runtime.scheduler.dependencies["lease_owner"]).startswith(
        "portfolio-derived-state-"
    )


async def test_runtime_ensures_owned_input_and_output_topics(
    patch_runtime: Callable[..., None],
    monkeypatch,
) -> None:
    ensured_topics: list[str] = []
    monkeypatch.setattr(
        runtime,
        "ensure_topics_exist",
        lambda topics: ensured_topics.extend(topics),
    )
    service_runtime = runtime.PortfolioDerivedStateRuntime()
    service_runtime._shutdown_event.set()

    await service_runtime.run()

    assert ensured_topics == [
        runtime.KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
        runtime.KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
        runtime.KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
    ]


async def test_runtime_gracefully_stops_all_components(
    patch_runtime: Callable[..., None],
) -> None:
    service_runtime = runtime.PortfolioDerivedStateRuntime()

    run_task = asyncio.create_task(service_runtime.run())
    await asyncio.sleep(0.05)
    service_runtime._shutdown_event.set()
    await asyncio.wait_for(run_task, timeout=2)

    assert service_runtime.consumers[0].shutdown_called is True
    assert service_runtime.scheduler.stop_called is True
    assert service_runtime.dispatcher.stop_called is True


@pytest.mark.parametrize("failing_component", ["consumer", "scheduler"])
async def test_runtime_fails_fast_and_stops_sibling_components(
    patch_runtime: Callable[..., None],
    failing_component: str,
) -> None:
    patch_runtime(
        consumer=_FakeFailingConsumer if failing_component == "consumer" else _FakeConsumer,
        scheduler=(_FakeFailingScheduler if failing_component == "scheduler" else _FakeScheduler),
    )
    service_runtime = runtime.PortfolioDerivedStateRuntime()

    with pytest.raises(RuntimeError, match="Critical service task"):
        await asyncio.wait_for(service_runtime.run(), timeout=2)

    assert service_runtime.consumers[0].shutdown_called is True
    assert service_runtime.scheduler.stop_called is True
    assert service_runtime.dispatcher.stop_called is True


async def test_settings_keep_aggregation_concurrency_and_lease_controls(monkeypatch) -> None:
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
