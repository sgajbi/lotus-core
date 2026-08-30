"""Verify transaction-neutral lot-disposal receipt mapping."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.query_service.app.services.lot_disposal_service import LotDisposalService
from tests.test_support.tenant import TEST_TENANT_CONTEXT


@pytest.mark.asyncio
async def test_latest_receipt_maps_ordered_allocations_and_lineage() -> None:
    receipt = SimpleNamespace(
        receipt_id="lot-disposal:abc",
        receipt_version=2,
        disposal_transaction_id="RED-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        disposal_timestamp=datetime(2026, 8, 4, tzinfo=UTC),
        transaction_type="PARTIAL_REDEMPTION",
        destination_type="INTERNAL_LOT",
        target_transaction_id="EXCHANGE-IN-001",
        target_lot_id="LOT-EXCHANGE-IN-001",
        target_instrument_id="BOND-2",
        external_destination_reference=None,
        cost_basis_method="FIFO",
        calculation_policy_id="REDEMPTION_FIFO_POLICY",
        calculation_policy_version="1.0.0",
        status="ACTIVE",
        void_reason=None,
        consumed_quantity=Decimal("25"),
        consumed_cost_local=Decimal("24.5"),
        consumed_cost_base=Decimal("18.375"),
        semantic_content_hash="a" * 64,
        previous_receipt_content_hash="b" * 64,
        receipt_content_hash="c" * 64,
        transaction_calculation_lineage={"algorithm_id": "transaction-cost"},
        disposal_calculation_lineage={"algorithm_id": "lot-disposal"},
    )
    allocation = SimpleNamespace(
        allocation_ordinal=1,
        source_lot_id="LOT-BUY-001",
        source_transaction_id="BUY-001",
        source_acquisition_date=date(2026, 1, 1),
        consumed_quantity=Decimal("25"),
        consumed_cost_local=Decimal("24.5"),
        consumed_cost_base=Decimal("18.375"),
        allocation_content_hash="d" * 64,
        amortized_cost_profile_id="PROFILE-1",
        amortized_cost_profile_version=1,
        amortized_cost_profile_content_hash="e" * 64,
        amortized_cost_currency="USD",
        amortized_cost_recognized_through=date(2026, 8, 4),
        amortized_cost_original_quantity=Decimal("100"),
        amortized_cost_open_quantity_before=Decimal("25"),
        amortized_cost_residual_quantity=Decimal("0"),
        amortized_cost_scheduled_local=Decimal("25"),
        amortized_cost_current_local=Decimal("24.5"),
        amortized_cost_current_base=Decimal("18.375"),
        amortized_cost_residual_local=Decimal("0"),
        amortized_cost_book_fx_rate_to_base=Decimal("0.75"),
        amortized_cost_residual_base=Decimal("0"),
        amortized_cost_retained_rounding_local=Decimal("0.5"),
        amortized_cost_retained_rounding_base=Decimal("0.375"),
        amortized_cost_calculation_lineage={"algorithm_id": "amortized-cost"},
    )
    repository = MagicMock()
    repository.portfolio_exists = AsyncMock(return_value=True)
    repository.get_latest_receipt = AsyncMock(return_value=(receipt, [allocation]))

    with patch(
        "src.services.query_service.app.services.lot_disposal_service.LotDisposalRepository",
        return_value=repository,
    ):
        result = await LotDisposalService(MagicMock()).get_latest_receipt(
            tenant_context=TEST_TENANT_CONTEXT,
            portfolio_id="P1",
            transaction_id="RED-001",
        )

    assert result.transaction_type == "PARTIAL_REDEMPTION"
    assert result.receipt_version == 2
    assert result.allocations[0].source_lot_id == "LOT-BUY-001"
    assert result.allocations[0].amortized_cost_profile_id == "PROFILE-1"
    assert result.allocations[0].model_dump(exclude_none=True) == {
        "allocation_ordinal": 1,
        "source_lot_id": "LOT-BUY-001",
        "source_transaction_id": "BUY-001",
        "source_acquisition_date": date(2026, 1, 1),
        "consumed_quantity": Decimal("25"),
        "consumed_cost_local": Decimal("24.5"),
        "consumed_cost_base": Decimal("18.375"),
        "allocation_content_hash": "d" * 64,
        "amortized_cost_profile_id": "PROFILE-1",
        "amortized_cost_profile_version": 1,
        "amortized_cost_profile_content_hash": "e" * 64,
        "amortized_cost_currency": "USD",
        "amortized_cost_recognized_through": date(2026, 8, 4),
        "amortized_cost_original_quantity": Decimal("100"),
        "amortized_cost_open_quantity_before": Decimal("25"),
        "amortized_cost_residual_quantity": Decimal("0"),
        "amortized_cost_scheduled_local": Decimal("25"),
        "amortized_cost_current_local": Decimal("24.5"),
        "amortized_cost_current_base": Decimal("18.375"),
        "amortized_cost_residual_local": Decimal("0"),
        "amortized_cost_book_fx_rate_to_base": Decimal("0.75"),
        "amortized_cost_residual_base": Decimal("0"),
        "amortized_cost_retained_rounding_local": Decimal("0.5"),
        "amortized_cost_retained_rounding_base": Decimal("0.375"),
        "amortized_cost_calculation_lineage": {"algorithm_id": "amortized-cost"},
    }
    assert result.disposal_calculation_lineage == {"algorithm_id": "lot-disposal"}
    assert result.destination_type == "INTERNAL_LOT"
    assert result.target_transaction_id == "EXCHANGE-IN-001"
    assert result.target_lot_id == "LOT-EXCHANGE-IN-001"
    assert result.target_instrument_id == "BOND-2"
    assert result.external_destination_reference is None


@pytest.mark.asyncio
async def test_latest_receipt_raises_when_transaction_has_no_receipt() -> None:
    repository = MagicMock()
    repository.portfolio_exists = AsyncMock(return_value=True)
    repository.get_latest_receipt = AsyncMock(return_value=None)
    with patch(
        "src.services.query_service.app.services.lot_disposal_service.LotDisposalRepository",
        return_value=repository,
    ):
        with pytest.raises(LookupError, match="RED-404"):
            await LotDisposalService(MagicMock()).get_latest_receipt(
                tenant_context=TEST_TENANT_CONTEXT,
                portfolio_id="P1",
                transaction_id="RED-404",
            )
