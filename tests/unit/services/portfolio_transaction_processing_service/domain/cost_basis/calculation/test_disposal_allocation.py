"""Verify immutable lot-disposal allocation contracts and conservation."""

from datetime import date
from decimal import Decimal

import pytest

from services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotDisposalResult,
    SourceLotDisposalAllocation,
)


def _allocation(
    *,
    source_transaction_id: str = "BUY_001",
    ordinal: int = 1,
    quantity: str = "2",
    local: str = "20",
    base: str = "22",
) -> SourceLotDisposalAllocation:
    return SourceLotDisposalAllocation(
        source_lot_id=f"LOT-{source_transaction_id}",
        source_transaction_id=source_transaction_id,
        source_acquisition_date=date(2026, 1, 2),
        allocation_ordinal=ordinal,
        consumed_quantity=Decimal(quantity),
        consumed_cost_local=Decimal(local),
        consumed_cost_base=Decimal(base),
    )


def test_result_requires_exact_source_lot_conservation() -> None:
    allocations = (
        _allocation(),
        _allocation(
            source_transaction_id="BUY_002",
            ordinal=2,
            quantity="3",
            local="36",
            base="39",
        ),
    )

    result = LotDisposalResult(
        cost_base=Decimal("61"),
        cost_local=Decimal("56"),
        consumed_quantity=Decimal("5"),
        allocations=allocations,
    )

    assert result.allocations == allocations
    assert result.allocations[0].source_lot_id == "LOT-BUY_001"
    assert result.allocations[0].source_acquisition_date == date(2026, 1, 2)
    assert result.legacy_tuple() == (
        Decimal("61"),
        Decimal("56"),
        Decimal("5"),
        None,
    )


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    (
        ("consumed_quantity", Decimal("4"), "quantity"),
        ("cost_local", Decimal("55"), "local cost"),
        ("cost_base", Decimal("60"), "base cost"),
    ),
)
def test_result_rejects_nonconserving_aggregates(
    field_name: str,
    value: Decimal,
    message: str,
) -> None:
    values = {
        "cost_base": Decimal("22"),
        "cost_local": Decimal("20"),
        "consumed_quantity": Decimal("2"),
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=message):
        LotDisposalResult(
            **values,
            allocations=(_allocation(),),
        )


def test_failed_result_cannot_carry_economics() -> None:
    with pytest.raises(ValueError, match="cannot carry economics"):
        LotDisposalResult(
            cost_base=Decimal("1"),
            cost_local=Decimal(0),
            consumed_quantity=Decimal(0),
            allocations=(),
            error_reason="insufficient quantity",
        )


def test_allocation_requires_contiguous_positive_ordinals() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        LotDisposalResult(
            cost_base=Decimal("22"),
            cost_local=Decimal("20"),
            consumed_quantity=Decimal("2"),
            allocations=(_allocation(ordinal=2),),
        )

    with pytest.raises(ValueError, match="positive"):
        _allocation(quantity="0")


def test_result_rejects_duplicate_source_lot_allocations() -> None:
    with pytest.raises(ValueError, match="source lot can appear only once"):
        LotDisposalResult(
            cost_base=Decimal("44"),
            cost_local=Decimal("40"),
            consumed_quantity=Decimal("4"),
            allocations=(_allocation(), _allocation(ordinal=2)),
        )
