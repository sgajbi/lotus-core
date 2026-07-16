"""Verify SQL transaction identity mapping for reprocessing commands."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from src.services.ingestion_service.app.infrastructure import (
    transaction_reprocessing_target_reader,
)
from src.services.ingestion_service.app.ports.transaction_reprocessing import (
    TransactionReprocessingTargetReadError,
)

pytestmark = pytest.mark.asyncio


async def test_reader_maps_authoritative_transaction_portfolios() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(transaction_id="TXN-1", portfolio_id="PORT-1"),
        SimpleNamespace(transaction_id="TXN-2", portfolio_id="PORT-2"),
    ]
    db.execute.return_value = result

    targets = (
        await transaction_reprocessing_target_reader.SqlAlchemyTransactionReprocessingTargetReader(
            db
        ).read_targets(["TXN-1", "TXN-2"])
    )

    assert [(target.transaction_id, target.portfolio_id) for target in targets] == [
        ("TXN-1", "PORT-1"),
        ("TXN-2", "PORT-2"),
    ]


async def test_reader_maps_database_failure_to_typed_port_error() -> None:
    db = AsyncMock()
    db.execute.side_effect = OperationalError("select", {}, RuntimeError("db unavailable"))

    with pytest.raises(
        TransactionReprocessingTargetReadError,
        match="source lookup is unavailable",
    ):
        await transaction_reprocessing_target_reader.SqlAlchemyTransactionReprocessingTargetReader(
            db
        ).read_targets(["TXN-1"])
