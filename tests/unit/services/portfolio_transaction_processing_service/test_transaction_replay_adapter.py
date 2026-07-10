from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    BookedTransactionReplayCardinalityError,
    SqlAlchemyBookedTransactionReplayAdapter,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("replayed_count", "expected"), [(0, False), (1, True)])
async def test_replay_adapter_maps_canonical_replay_count(
    replayed_count: int,
    expected: bool,
) -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    session_factory = MagicMock(return_value=session)
    replayer = AsyncMock()
    replayer.reprocess_transactions_by_ids.return_value = replayed_count
    replayer_factory = MagicMock(return_value=replayer)
    adapter = SqlAlchemyBookedTransactionReplayAdapter(
        session_factory=session_factory,
        replayer_factory=replayer_factory,
    )

    replayed = await adapter.replay_booked_transaction(
        transaction_id="TXN-REPLAY-01",
        correlation_id="corr-replay-01",
    )

    assert replayed is expected
    session_factory.assert_called_once_with()
    replayer_factory.assert_called_once_with(session)
    replayer.reprocess_transactions_by_ids.assert_awaited_once_with(
        ["TXN-REPLAY-01"],
        correlation_id="corr-replay-01",
    )
    session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_replay_adapter_rejects_impossible_unique_transaction_cardinality() -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    replayer = AsyncMock()
    replayer.reprocess_transactions_by_ids.return_value = 2
    adapter = SqlAlchemyBookedTransactionReplayAdapter(
        session_factory=MagicMock(return_value=session),
        replayer_factory=MagicMock(return_value=replayer),
    )

    with pytest.raises(BookedTransactionReplayCardinalityError, match="zero or one record"):
        await adapter.replay_booked_transaction(
            transaction_id="TXN-REPLAY-DUPLICATE",
            correlation_id=None,
        )
