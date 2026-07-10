from decimal import Decimal

import pytest
from cost_engine.processing.average_cost_source_allocation import (
    AverageCostPool,
    AverageCostSourceAllocation,
)


def test_average_cost_disposals_do_not_rewrite_source_contributions() -> None:
    allocation = AverageCostSourceAllocation()
    book_key = ("P1", "I1")
    for index in range(100):
        allocation.add_source(
            book_key=book_key,
            source_transaction_id=f"BUY-{index:03d}",
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
