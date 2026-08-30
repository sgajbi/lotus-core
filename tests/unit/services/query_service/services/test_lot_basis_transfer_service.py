"""Verify transaction-neutral lot basis-transfer receipt mapping."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.query_service.app.services.lot_basis_transfer_service import (
    LotBasisTransferService,
)
from tests.test_support.tenant import TEST_TENANT_CONTEXT


def _receipt() -> SimpleNamespace:
    return SimpleNamespace(
        receipt_id="lot-basis-transfer:abc",
        receipt_version=2,
        source_transaction_id="DEMERGER-OUT-001",
        target_transaction_id="DEMERGER-IN-001",
        target_lot_id="LOT-DEMERGER-IN-001",
        portfolio_id="P1",
        source_instrument_id="BOND-1",
        source_security_id="BOND-1",
        target_instrument_id="EQUITY-1",
        transfer_timestamp=datetime(2026, 8, 4, tzinfo=UTC),
        transaction_type="DEMERGER_OUT",
        cost_basis_method="FIFO",
        calculation_policy_id="CORPORATE_ACTION_FIFO_POLICY",
        calculation_policy_version="1.0.0",
        status="ACTIVE",
        void_reason=None,
        transferred_cost_local=Decimal("25"),
        transferred_cost_base=Decimal("18.75"),
        allocation_count=1,
        semantic_content_hash="a" * 64,
        previous_receipt_content_hash="b" * 64,
        receipt_content_hash="c" * 64,
        transaction_calculation_lineage={"algorithm_id": "transaction-cost"},
        basis_transfer_calculation_lineage={"algorithm_id": "basis-transfer"},
    )


def _allocation() -> SimpleNamespace:
    return SimpleNamespace(
        allocation_ordinal=1,
        source_lot_id="LOT-BUY-001",
        source_transaction_id="BUY-001",
        source_acquisition_date=date(2026, 1, 1),
        retained_quantity=Decimal("75"),
        source_cost_local_before=Decimal("100"),
        source_cost_base_before=Decimal("75"),
        transferred_cost_local=Decimal("25"),
        transferred_cost_base=Decimal("18.75"),
        retained_cost_local=Decimal("75"),
        retained_cost_base=Decimal("56.25"),
        allocation_content_hash="d" * 64,
    )


@pytest.mark.asyncio
async def test_latest_receipt_maps_target_and_conserved_source_lot_economics() -> None:
    repository = MagicMock()
    repository.portfolio_exists = AsyncMock(return_value=True)
    repository.get_latest_receipt = AsyncMock(return_value=(_receipt(), [_allocation()]))

    with patch(
        "src.services.query_service.app.services.lot_basis_transfer_service."
        "LotBasisTransferRepository",
        return_value=repository,
    ):
        result = await LotBasisTransferService(MagicMock()).get_latest_receipt(
            tenant_context=TEST_TENANT_CONTEXT,
            portfolio_id="P1",
            source_transaction_id="DEMERGER-OUT-001",
        )

    assert result.target_transaction_id == "DEMERGER-IN-001"
    assert result.target_lot_id == "LOT-DEMERGER-IN-001"
    assert result.basis_transfer_calculation_lineage == {"algorithm_id": "basis-transfer"}
    assert result.allocations[0].source_cost_local_before == Decimal("100")
    assert result.allocations[0].transferred_cost_local == Decimal("25")
    assert result.allocations[0].retained_cost_local == Decimal("75")


@pytest.mark.asyncio
async def test_latest_receipt_raises_when_source_transaction_has_no_receipt() -> None:
    repository = MagicMock()
    repository.portfolio_exists = AsyncMock(return_value=True)
    repository.get_latest_receipt = AsyncMock(return_value=None)
    with patch(
        "src.services.query_service.app.services.lot_basis_transfer_service."
        "LotBasisTransferRepository",
        return_value=repository,
    ):
        with pytest.raises(LookupError, match="DEMERGER-OUT-404"):
            await LotBasisTransferService(MagicMock()).get_latest_receipt(
                tenant_context=TEST_TENANT_CONTEXT,
                portfolio_id="P1",
                source_transaction_id="DEMERGER-OUT-404",
            )
