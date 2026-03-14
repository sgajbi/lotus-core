import asyncio

import pytest
from portfolio_common import kafka_consumer as shared_kafka_consumer
from portfolio_common.kafka_admin import KafkaTopicVerificationError

from src.services.valuation_orchestrator_service.app import consumer_manager

pytestmark = pytest.mark.asyncio


class _FakeScheduler:
    def __init__(self):
        self.stop_called = False
        self._stop_event = asyncio.Event()

    async def run(self):
        await self._stop_event.wait()

    def stop(self):
        self.stop_called = True
        self._stop_event.set()


class _FakeReprocessingWorker(_FakeScheduler):
    pass


class _FakeServer:
    def __init__(self, _config):
        self.should_exit = False

    async def serve(self):
        while not self.should_exit:
            await asyncio.sleep(0.01)


class _FakeSuccessConsumer:
    def __init__(self, **kwargs):
        self.topic = kwargs["topic"]
        self.shutdown_called = False
        self._stop_event = asyncio.Event()

    async def run(self):
        await self._stop_event.wait()

    def shutdown(self):
        self.shutdown_called = True
        self._stop_event.set()


class _FakeFailingConsumer(_FakeSuccessConsumer):
    async def run(self):
        raise ValueError("simulated-valuation-orchestrator-consumer-failure")


@pytest.fixture
def _patch_runtime(monkeypatch):
    monkeypatch.setattr(consumer_manager, "ensure_topics_exist", lambda *_: None)
    monkeypatch.setattr(consumer_manager.signal, "signal", lambda *_: None)
    monkeypatch.setattr(consumer_manager, "ValuationScheduler", _FakeScheduler)
    monkeypatch.setattr(consumer_manager, "ReprocessingWorker", _FakeReprocessingWorker)
    monkeypatch.setattr(consumer_manager.uvicorn, "Config", lambda *args, **kwargs: object())
    monkeypatch.setattr(consumer_manager.uvicorn, "Server", _FakeServer)


async def test_consumer_manager_graceful_shutdown(_patch_runtime, monkeypatch):
    monkeypatch.setattr(consumer_manager, "ValuationReadinessConsumer", _FakeSuccessConsumer)
    monkeypatch.setattr(consumer_manager, "PriceEventConsumer", _FakeSuccessConsumer)
    manager = consumer_manager.ConsumerManager()

    run_task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.05)
    manager._shutdown_event.set()
    await asyncio.wait_for(run_task, timeout=2)

    assert all(c.shutdown_called for c in manager.consumers)
    assert manager.scheduler.stop_called is True
    assert manager.reprocessing_worker.stop_called is True


async def test_consumer_manager_fails_fast_on_task_crash(_patch_runtime, monkeypatch):
    monkeypatch.setattr(consumer_manager, "ValuationReadinessConsumer", _FakeFailingConsumer)
    monkeypatch.setattr(consumer_manager, "PriceEventConsumer", _FakeSuccessConsumer)
    manager = consumer_manager.ConsumerManager()

    with pytest.raises(RuntimeError, match="Critical service task"):
        await asyncio.wait_for(manager.run(), timeout=2)

    assert manager.scheduler.stop_called is True
    assert manager.reprocessing_worker.stop_called is True


async def test_consumer_manager_propagates_typed_topic_verification_failure(
    _patch_runtime, monkeypatch
):
    monkeypatch.setattr(consumer_manager, "ValuationReadinessConsumer", _FakeSuccessConsumer)
    monkeypatch.setattr(consumer_manager, "PriceEventConsumer", _FakeSuccessConsumer)
    monkeypatch.setattr(
        consumer_manager,
        "ensure_topics_exist",
        lambda *_: (_ for _ in ()).throw(KafkaTopicVerificationError("topics unavailable")),
    )
    manager = consumer_manager.ConsumerManager()

    with pytest.raises(KafkaTopicVerificationError, match="topics unavailable"):
        await manager.run()

    assert manager.tasks == []
    assert manager.scheduler.stop_called is False
    assert manager.reprocessing_worker.stop_called is False


async def test_consumer_manager_applies_only_valid_merged_runtime_overrides(
    _patch_runtime, monkeypatch
):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
        '{"session.timeout.ms": 30000}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
        '{"valuation_orchestrator_group_readiness": {"heartbeat.interval.ms": 30000}}',
    )
    monkeypatch.setattr(shared_kafka_consumer, "get_kafka_producer", lambda: object())

    manager = consumer_manager.ConsumerManager()
    readiness_consumer = next(
        c
        for c in manager.consumers
        if c._consumer_config["group.id"] == "valuation_orchestrator_group_readiness"
    )
    price_consumer = next(
        c
        for c in manager.consumers
        if c._consumer_config["group.id"] == "valuation_orchestrator_group_price_events"
    )

    assert readiness_consumer._consumer_config["session.timeout.ms"] == 30000
    assert readiness_consumer._consumer_config["heartbeat.interval.ms"] == 3000
    assert price_consumer._consumer_config["session.timeout.ms"] == 30000
    assert price_consumer._consumer_config["heartbeat.interval.ms"] == 3000
