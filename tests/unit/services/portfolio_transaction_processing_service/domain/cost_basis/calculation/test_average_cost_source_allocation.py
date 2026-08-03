"""Verify domain-owned average-cost source allocation policy."""

from datetime import date
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AverageCostPool,
    AverageCostSourceAllocation,
    OpenLotState,
)


def test_average_cost_disposals_do_not_rewrite_source_contributions() -> None:
    allocation = AverageCostSourceAllocation()
    book_key = ("P1", "I1")
    for index in range(100):
        allocation.add_source(
            book_key=book_key,
            source_transaction_id=f"BUY-{index:03d}",
            source_lot_id=f"LOT-BUY-{index:03d}",
            source_acquisition_date=date(2026, 1, 1),
            quantity=Decimal("1"),
            cost_local=Decimal("10"),
            cost_base=Decimal("12"),
            pool_quantity_after=Decimal(index + 1),
        )
    contributions_before = dict(allocation._contributions)

    quantity = Decimal("100")
    for _ in range(10):
        allocation.apply_disposal(
            book_key=book_key,
            quantity_before=quantity,
            quantity_after=quantity - Decimal("1"),
        )
        quantity -= Decimal("1")

    assert allocation._contributions == contributions_before
    states = allocation.materialize(
        {
            book_key: AverageCostPool(
                quantity=Decimal("90"),
                cost_local=Decimal("900"),
                cost_base=Decimal("1080"),
            )
        }
    )
    assert sum(state.quantity for state in states.values()) == Decimal("90")
    assert sum(state.cost_local for state in states.values()) == Decimal("900")
    assert sum(state.cost_base for state in states.values()) == Decimal("1080")


def test_materialize_book_is_bounded_to_requested_book() -> None:
    allocation = AverageCostSourceAllocation()
    for book_key, source_id in (("I1", "BUY-1"), ("I2", "BUY-2")):
        allocation.add_source(
            book_key=("P1", book_key),
            source_transaction_id=source_id,
            source_lot_id=f"LOT-{source_id}",
            source_acquisition_date=date(2026, 1, 1),
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("120"),
            pool_quantity_after=Decimal("10"),
        )

    states = allocation.materialize_book(
        book_key=("P1", "I1"),
        pool=AverageCostPool(
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("120"),
        ),
    )

    assert states == {
        "BUY-1": OpenLotState(
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("120"),
        )
    }


def test_materialize_book_does_not_scan_unrelated_source_map() -> None:
    class IterationForbiddenDict(dict):
        def items(self):
            raise AssertionError("book materialization must not scan all source contributions")

        def values(self):
            raise AssertionError("book materialization must not scan all source contributions")

    allocation = AverageCostSourceAllocation()
    for instrument_id, source_id in (("I1", "BUY-1"), ("I2", "BUY-2")):
        allocation.add_source(
            book_key=("P1", instrument_id),
            source_transaction_id=source_id,
            source_lot_id=f"LOT-{source_id}",
            source_acquisition_date=date(2026, 1, 1),
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("120"),
            pool_quantity_after=Decimal("10"),
        )
    allocation._contributions = IterationForbiddenDict(allocation._contributions)

    states = allocation.materialize_book(
        book_key=("P1", "I1"),
        pool=AverageCostPool(
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("120"),
        ),
    )

    assert tuple(states) == ("BUY-1",)


def test_average_cost_source_identity_must_be_unique() -> None:
    allocation = AverageCostSourceAllocation()
    values = {
        "book_key": ("P1", "I1"),
        "source_transaction_id": "BUY-1",
        "source_lot_id": "LOT-BUY-1",
        "source_acquisition_date": date(2026, 1, 1),
        "quantity": Decimal("10"),
        "cost_local": Decimal("100"),
        "cost_base": Decimal("120"),
        "pool_quantity_after": Decimal("10"),
    }
    allocation.add_source(**values)

    with pytest.raises(ValueError, match="identity must be unique"):
        allocation.add_source(**values)


@pytest.mark.parametrize(
    ("quantity_before", "quantity_after", "message"),
    [
        (Decimal("0"), Decimal("0"), "positive quantity_before"),
        (Decimal("10"), Decimal("-1"), "outside the pool"),
        (Decimal("10"), Decimal("11"), "outside the pool"),
    ],
)
def test_average_cost_source_allocation_rejects_invalid_disposal_bounds(
    quantity_before: Decimal,
    quantity_after: Decimal,
    message: str,
) -> None:
    allocation = AverageCostSourceAllocation()

    with pytest.raises(ValueError, match=message):
        allocation.apply_disposal(
            book_key=("P1", "I1"),
            quantity_before=quantity_before,
            quantity_after=quantity_after,
        )
