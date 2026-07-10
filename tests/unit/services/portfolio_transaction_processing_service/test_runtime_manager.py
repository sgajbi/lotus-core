from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.runtime import manager


@pytest.mark.asyncio
async def test_combined_manager_delegates_six_consumers_to_shared_runtime(monkeypatch) -> None:
    consumers = [MagicMock(topic=f"topic-{index}") for index in range(6)]
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
