import asyncio

import pytest

from src.services.financial_reconciliation_service.app import consumer_manager

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
        raise ValueError("simulated-reconciliation-consumer-failure")


@pytest.fixture
def _patch_runtime(monkeypatch):
    monkeypatch.setattr(consumer_manager, "ensure_topics_exist", lambda *_: None)
    monkeypatch.setattr(consumer_manager.signal, "signal", lambda *_: None)
    monkeypatch.setattr(consumer_manager, "get_kafka_producer", lambda: object())
    monkeypatch.setattr(consumer_manager, "OutboxDispatcher", _FakeDispatcher)
    monkeypatch.setattr(consumer_manager.uvicorn, "Config", lambda *args, **kwargs: object())
    monkeypatch.setattr(consumer_manager.uvicorn, "Server", _FakeServer)


async def test_consumer_manager_graceful_shutdown(_patch_runtime, monkeypatch):
    monkeypatch.setattr(consumer_manager, "ReconciliationRequestedConsumer", _FakeSuccessConsumer)
    manager = consumer_manager.ConsumerManager()

    run_task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.05)
    manager._shutdown_event.set()
    await asyncio.wait_for(run_task, timeout=2)

    assert all(c.shutdown_called for c in manager.consumers)
    assert manager.dispatcher.stop_called is True


async def test_consumer_manager_fails_fast_on_task_crash(_patch_runtime, monkeypatch):
    monkeypatch.setattr(consumer_manager, "ReconciliationRequestedConsumer", _FakeFailingConsumer)
    manager = consumer_manager.ConsumerManager()

    with pytest.raises(RuntimeError, match="Critical service task"):
        await asyncio.wait_for(manager.run(), timeout=2)

    assert manager.dispatcher.stop_called is True
