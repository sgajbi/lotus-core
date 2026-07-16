"""Verify source-owned transaction reprocessing target resolution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.ingestion_service.app.application import (
    ResolveTransactionReprocessingTargets,
    TransactionReprocessingTargetNotFound,
)
from src.services.ingestion_service.app.domain import TransactionReprocessingTarget

pytestmark = pytest.mark.asyncio


async def test_resolver_preserves_requested_order() -> None:
    reader = SimpleNamespace(
        read_targets=AsyncMock(
            return_value=(
                TransactionReprocessingTarget(
                    transaction_id="TXN-2",
                    portfolio_id="PORT-2",
                ),
                TransactionReprocessingTarget(
                    transaction_id="TXN-1",
                    portfolio_id="PORT-1",
                ),
            )
        )
    )

    targets = await ResolveTransactionReprocessingTargets(reader).execute(["TXN-1", "TXN-2"])

    assert [target.transaction_id for target in targets] == ["TXN-1", "TXN-2"]
    assert [target.portfolio_id for target in targets] == ["PORT-1", "PORT-2"]


async def test_resolver_rejects_missing_transactions_before_publication() -> None:
    reader = SimpleNamespace(
        read_targets=AsyncMock(
            return_value=(
                TransactionReprocessingTarget(
                    transaction_id="TXN-1",
                    portfolio_id="PORT-1",
                ),
            )
        )
    )

    with pytest.raises(TransactionReprocessingTargetNotFound) as exc_info:
        await ResolveTransactionReprocessingTargets(reader).execute(["TXN-1", "TXN-404"])

    assert exc_info.value.missing_transaction_ids == ("TXN-404",)
    assert exc_info.value.reason_code == "INGESTION_REPROCESSING_SOURCE_NOT_FOUND"
