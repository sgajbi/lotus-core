from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools import reprocess_transactions as tool_module

pytestmark = pytest.mark.asyncio


class _FakeBegin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeSession:
    def begin(self):
        return _FakeBegin()


class _FakeDbSessions:
    def __aiter__(self):
        self._yielded = False
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return _FakeSession()


async def test_main_warns_and_exits_when_no_transaction_ids():
    with (
        patch.object(tool_module, "get_kafka_producer") as get_kafka_producer,
        patch.object(tool_module.logger, "warning") as logger_warning,
    ):
        await tool_module.main([])

    get_kafka_producer.assert_not_called()
    logger_warning.assert_called_once_with("No transaction IDs provided. Exiting.")


async def test_main_raises_when_final_flush_leaves_undelivered_messages():
    producer = MagicMock()
    producer.flush.return_value = 1
    repo_instance = MagicMock()
    repo_instance.reprocess_transactions_by_ids = AsyncMock(return_value=2)

    with (
        patch.object(tool_module, "get_kafka_producer", return_value=producer),
        patch.object(tool_module, "get_async_db_session", lambda: _FakeDbSessions()),
        patch.object(tool_module, "ReprocessingRepository", return_value=repo_instance),
        patch.object(tool_module.logger, "info") as logger_info,
    ):
        with pytest.raises(RuntimeError, match="undelivered message"):
            await tool_module.main(["TXN_A", "TXN_B"])

    repo_instance.reprocess_transactions_by_ids.assert_awaited_once_with(
        transaction_ids=["TXN_A", "TXN_B"]
    )
    producer.flush.assert_called_once_with(timeout=10)
    logged_messages = [args[0] for args, _ in logger_info.call_args_list]
    assert not any("Completed reprocessing." in message for message in logged_messages)


async def test_main_preserves_original_reprocessing_error_when_cleanup_flush_times_out():
    producer = MagicMock()
    producer.flush.return_value = 1
    repo_instance = MagicMock()
    repo_instance.reprocess_transactions_by_ids = AsyncMock(
        side_effect=RuntimeError("republish failed")
    )

    with (
        patch.object(tool_module, "get_kafka_producer", return_value=producer),
        patch.object(tool_module, "get_async_db_session", lambda: _FakeDbSessions()),
        patch.object(tool_module, "ReprocessingRepository", return_value=repo_instance),
        patch.object(tool_module.logger, "exception") as logger_exception,
    ):
        with pytest.raises(RuntimeError, match="republish failed"):
            await tool_module.main(["TXN_A"])

    producer.flush.assert_called_once_with(timeout=10)
    logger_exception.assert_called_once_with(
        "Kafka producer flush failed during reprocessing cleanup."
    )
