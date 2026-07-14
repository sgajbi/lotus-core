"""Verify canonical booked transaction replay adaptation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.reprocessing_replay import ReprocessingReplayError
from sqlalchemy.exc import DBAPIError

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayInvariantViolation,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
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

    with pytest.raises(BookedTransactionReplayInvariantViolation, match="zero or one record"):
        await adapter.replay_booked_transaction(
            transaction_id="TXN-REPLAY-DUPLICATE",
            correlation_id=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency_error",
    [
        DBAPIError("SELECT", {}, RuntimeError("database unavailable")),
        ReprocessingReplayError(
            "publisher unavailable",
            failed_transaction_ids=["TXN-REPLAY-01"],
        ),
    ],
)
async def test_replay_adapter_maps_infrastructure_dependency_failures(
    dependency_error: Exception,
) -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    replayer = AsyncMock()
    replayer.reprocess_transactions_by_ids.side_effect = dependency_error
    adapter = SqlAlchemyBookedTransactionReplayAdapter(
        session_factory=MagicMock(return_value=session),
        replayer_factory=MagicMock(return_value=replayer),
    )

    with pytest.raises(BookedTransactionReplayDependencyUnavailable) as exc_info:
        await adapter.replay_booked_transaction(
            transaction_id="TXN-REPLAY-01",
            correlation_id="corr-replay-01",
        )

    assert exc_info.value.__cause__ is dependency_error
