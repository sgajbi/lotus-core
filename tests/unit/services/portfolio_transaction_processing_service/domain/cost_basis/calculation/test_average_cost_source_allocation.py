"""Verify domain-owned average-cost source allocation policy."""

from datetime import date
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AverageCostPool,
    AverageCostSourceAllocation,
    OpenLotState,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis.calculation.average_cost_source_allocation import (
    AverageCostSourceContribution,
    _assign_quantity_residual,
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


def test_quantity_residual_never_revives_a_stale_generation() -> None:
    book_key = ("P1", "I1")

    def contribution(source_id: str, generation: int) -> AverageCostSourceContribution:
        return AverageCostSourceContribution(
            book_key=book_key,
            source_lot_id=f"LOT-{source_id}",
            source_acquisition_date=date(2026, 1, 1),
            generation=generation,
            original_quantity=Decimal("1"),
            quantity=Decimal("1"),
            cost_local=Decimal("10"),
            cost_base=Decimal("10"),
            disposal_scale_at_entry=Decimal("1"),
            cost_local_scale_at_entry=Decimal("1"),
            cost_base_scale_at_entry=Decimal("1"),
            cost_local_generation=generation,
            cost_base_generation=generation,
        )

    quantities = {"CURRENT": Decimal(0), "STALE": Decimal(0)}
    _assign_quantity_residual(
        contributions=(
            ("CURRENT", contribution("CURRENT", 2)),
            ("STALE", contribution("STALE", 1)),
        ),
        quantities=quantities,
        current_generation=2,
        aggregate=Decimal("1"),
        allocated=Decimal(0),
    )

    assert quantities == {"CURRENT": Decimal("1"), "STALE": Decimal(0)}


def test_materialize_distributes_residual_within_each_source_original_quantity() -> None:
    allocation = AverageCostSourceAllocation()
    book_key = ("P1", "I1")
    pool = AverageCostPool()

    for index in range(3):
        pool.add(quantity=Decimal("1"), cost_local=Decimal("10"), cost_base=Decimal("10"))
        allocation.add_source(
            book_key=book_key,
            source_transaction_id=f"BUY-EARLY-{index}",
            source_lot_id=f"LOT-EARLY-{index}",
            source_acquisition_date=date(2026, 1, 1),
            quantity=Decimal("1"),
            cost_local=Decimal("10"),
            cost_base=Decimal("10"),
            pool_quantity_after=pool.quantity,
        )
    allocation.apply_disposal(
        book_key=book_key,
        quantity_before=Decimal("3"),
        quantity_after=Decimal("2"),
    )
    pool.quantity = Decimal("2")
    pool.cost_local = Decimal("20")
    pool.cost_base = Decimal("20")

    for index in range(3):
        pool.add(quantity=Decimal("1"), cost_local=Decimal("10"), cost_base=Decimal("10"))
        allocation.add_source(
            book_key=book_key,
            source_transaction_id=f"BUY-LATE-{index}",
            source_lot_id=f"LOT-LATE-{index}",
            source_acquisition_date=date(2026, 1, 2),
            quantity=Decimal("1"),
            cost_local=Decimal("10"),
            cost_base=Decimal("10"),
            pool_quantity_after=pool.quantity,
        )
    allocation.apply_disposal(
        book_key=book_key,
        quantity_before=Decimal("5"),
        quantity_after=Decimal("4"),
    )
    pool.quantity = Decimal("4")
    pool.cost_local = Decimal("40")
    pool.cost_base = Decimal("40")

    states = allocation.materialize_book(book_key=book_key, pool=pool)

    assert sum((state.quantity for state in states.values()), Decimal(0)) == Decimal("4")
    assert all(state.quantity <= state.original_quantity for state in states.values())
    assert [state.quantity for state in states.values()] == [
        Decimal("0.5333333333"),
        Decimal("0.5333333333"),
        Decimal("0.5333333333"),
        Decimal("0.8000000000"),
        Decimal("0.8000000000"),
        Decimal("0.8000000001"),
    ]


def test_materialize_rejects_pool_quantity_beyond_source_authority() -> None:
    allocation = AverageCostSourceAllocation()
    book_key = ("P1", "I1")
    allocation.add_source(
        book_key=book_key,
        source_transaction_id="BUY-1",
        source_lot_id="LOT-BUY-1",
        source_acquisition_date=date(2026, 1, 1),
        quantity=Decimal("1"),
        original_quantity=Decimal("0.5"),
        cost_local=Decimal("10"),
        cost_base=Decimal("10"),
        pool_quantity_after=Decimal("1"),
    )

    with pytest.raises(ValueError, match="exceeds source original quantity authority"):
        allocation.materialize_book(
            book_key=book_key,
            pool=AverageCostPool(
                quantity=Decimal("1"),
                cost_local=Decimal("10"),
                cost_base=Decimal("10"),
            ),
        )


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
            original_quantity=Decimal("10"),
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


def test_closed_generations_are_not_scanned_during_later_disposals() -> None:
    class HistoricalIterationForbiddenList(list[str]):
        def __iter__(self):
            raise AssertionError("disposal materialization must not scan closed generations")

        def __reversed__(self):
            raise AssertionError("disposal materialization must not scan closed generations")

    allocation = AverageCostSourceAllocation()
    book_key = ("P1", "I1")
    pool = AverageCostPool()

    allocation.add_source(
        book_key=book_key,
        source_transaction_id="BUY-CLOSED",
        source_lot_id="LOT-BUY-CLOSED",
        source_acquisition_date=date(2026, 1, 1),
        quantity=Decimal("1"),
        cost_local=Decimal("10"),
        cost_base=Decimal("12"),
        pool_quantity_after=Decimal("1"),
    )
    allocation.apply_disposal(
        book_key=book_key,
        quantity_before=Decimal("1"),
        quantity_after=Decimal("0"),
    )
    allocation._source_ids_by_key[book_key] = HistoricalIterationForbiddenList(
        allocation._source_ids_by_key[book_key]
    )

    pool.add(quantity=Decimal("2"), cost_local=Decimal("20"), cost_base=Decimal("24"))
    allocation.add_source(
        book_key=book_key,
        source_transaction_id="BUY-ACTIVE",
        source_lot_id="LOT-BUY-ACTIVE",
        source_acquisition_date=date(2026, 1, 2),
        quantity=Decimal("2"),
        cost_local=Decimal("20"),
        cost_base=Decimal("24"),
        pool_quantity_after=Decimal("2"),
    )

    assert allocation.materialize_book(book_key=book_key, pool=pool) == {
        "BUY-ACTIVE": OpenLotState(
            original_quantity=Decimal("2"),
            quantity=Decimal("2"),
            cost_local=Decimal("20"),
            cost_base=Decimal("24"),
        )
    }
    active_source_ids = tuple(
        source_id for source_id, _ in allocation.active_source_contributions(book_key)
    )
    assert active_source_ids == ("BUY-ACTIVE",)


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
