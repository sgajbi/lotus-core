from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.runtime import manager


@pytest.mark.asyncio
async def test_combined_manager_delegates_consumers_to_shared_runtime(monkeypatch) -> None:
    consumers = [MagicMock(topic=f"topic-{index}") for index in range(2)]
    dispatcher = MagicMock()
    run_runtime = AsyncMock()
    monkeypatch.setattr(manager, "run_kafka_worker_runtime", run_runtime)

    runtime_manager = manager.ConsumerManager(consumers=consumers, dispatcher=dispatcher)
    await runtime_manager.run()

    call = run_runtime.await_args.kwargs
    assert call["consumers"] == consumers
    assert call["dispatcher"] is dispatcher
    assert call["web_port"] == 8085
    assert call["readiness_service_name"] == "portfolio_transaction_processing_service_web"


def test_combined_manager_defaults_to_final_two_consumer_composition(monkeypatch) -> None:
    target_consumers = (
        MagicMock(topic="transactions.persisted"),
        MagicMock(topic="transactions.reprocessing.requested"),
    )
    build_consumers = MagicMock(return_value=target_consumers)
    dispatcher = MagicMock()
    monkeypatch.setattr(
        manager,
        "build_transaction_processing_consumers",
        build_consumers,
    )

    runtime_manager = manager.ConsumerManager(dispatcher=dispatcher)

    assert runtime_manager.consumers == list(target_consumers)
    assert runtime_manager.dispatcher is dispatcher
    build_consumers.assert_called_once_with()


def test_combined_manager_preserves_intentionally_empty_injected_components(monkeypatch) -> None:
    build_consumers = MagicMock()
    monkeypatch.setattr(
        manager,
        "build_transaction_processing_consumers",
        build_consumers,
    )
    dispatcher = MagicMock()

    runtime_manager = manager.ConsumerManager(consumers=[], dispatcher=dispatcher)

    assert runtime_manager.consumers == []
    assert runtime_manager.dispatcher is dispatcher
    build_consumers.assert_not_called()
