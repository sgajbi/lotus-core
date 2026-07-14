"""Verify booked-transaction replay application behavior and status mapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayStatus,
    ReplayBookedTransactionCommand,
    ReplayBookedTransactionUseCase,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("replayed", "expected_status"),
    [
        (True, BookedTransactionReplayStatus.REPLAYED),
        (False, BookedTransactionReplayStatus.NOT_FOUND),
    ],
)
async def test_replay_booked_transaction_returns_explicit_status(
    replayed: bool,
    expected_status: BookedTransactionReplayStatus,
) -> None:
    replay_port = AsyncMock()
    replay_port.replay_booked_transaction.return_value = replayed
    observation = MagicMock()
    observer = MagicMock()
    observer.observe.return_value.__enter__.return_value = observation
    use_case = ReplayBookedTransactionUseCase(replay_port, observer=observer)

    result = await use_case.execute(
        ReplayBookedTransactionCommand(
            transaction_id=" TXN-REPLAY-01 ",
            correlation_id="corr-replay-01",
        )
    )

    assert result.transaction_id == "TXN-REPLAY-01"
    assert result.status is expected_status
    replay_port.replay_booked_transaction.assert_awaited_once_with(
        transaction_id="TXN-REPLAY-01",
        correlation_id="corr-replay-01",
    )
    observer.observe.assert_called_once_with(TransactionProcessingOperation.REPLAY)
    observation.set_outcome.assert_called_once_with(
        TransactionProcessingOutcome(expected_status.value)
    )


def test_replay_booked_transaction_rejects_blank_transaction_id() -> None:
    with pytest.raises(ValueError, match="requires a transaction_id"):
        ReplayBookedTransactionCommand(transaction_id="  ")
