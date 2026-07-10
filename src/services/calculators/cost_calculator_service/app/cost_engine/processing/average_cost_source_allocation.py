from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from .cost_objects import OpenLotState

BookKey = tuple[str, str]
LOT_QUANTITY_QUANTUM = Decimal("0.0000000001")


@dataclass(slots=True)
class AverageCostPool:
    quantity: Decimal = Decimal(0)
    cost_local: Decimal = Decimal(0)
    cost_base: Decimal = Decimal(0)
    segment_start_quantity: Decimal = Decimal(0)
    segment_start_cost_local: Decimal = Decimal(0)
    segment_start_cost_base: Decimal = Decimal(0)

    def add(self, *, quantity: Decimal, cost_local: Decimal, cost_base: Decimal) -> None:
        self.quantity += quantity
        self.cost_local += cost_local
        self.cost_base += cost_base
        self.segment_start_quantity = self.quantity
        self.segment_start_cost_local = self.cost_local
        self.segment_start_cost_base = self.cost_base

    def dispose(self, quantity: Decimal) -> tuple[Decimal, Decimal]:
        cost_local_before = self.cost_local
        cost_base_before = self.cost_base
        quantity_after = self.quantity - quantity
        if quantity_after.is_zero():
            self.cost_local = Decimal(0)
            self.cost_base = Decimal(0)
        else:
            self.cost_local = (
                self.segment_start_cost_local * quantity_after / self.segment_start_quantity
            )
            self.cost_base = (
                self.segment_start_cost_base * quantity_after / self.segment_start_quantity
            )
        self.quantity = quantity_after
        return cost_base_before - self.cost_base, cost_local_before - self.cost_local


@dataclass(frozen=True, slots=True)
class AverageCostSourceContribution:
    book_key: BookKey
    generation: int
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal
    disposal_scale_at_entry: Decimal


class AverageCostSourceAllocation:
    """Lazily scale AVCO source contributions and materialize exact aggregate state once."""

    def __init__(self) -> None:
        self._contributions: dict[str, AverageCostSourceContribution] = {}
        self._generation_by_key: dict[BookKey, int] = defaultdict(int)
        self._disposal_scale_by_key: dict[BookKey, Decimal] = defaultdict(lambda: Decimal(1))
        self._segment_start_scale_by_key: dict[BookKey, Decimal] = defaultdict(lambda: Decimal(1))
        self._segment_start_quantity_by_key: dict[BookKey, Decimal] = defaultdict(Decimal)

    def add_source(
        self,
        *,
        book_key: BookKey,
        source_transaction_id: str,
        quantity: Decimal,
        cost_local: Decimal,
        cost_base: Decimal,
        pool_quantity_after: Decimal,
    ) -> None:
        self._contributions[source_transaction_id] = AverageCostSourceContribution(
            book_key=book_key,
            generation=self._generation_by_key[book_key],
            quantity=quantity,
            cost_local=cost_local,
            cost_base=cost_base,
            disposal_scale_at_entry=self._disposal_scale_by_key[book_key],
        )
        self._segment_start_scale_by_key[book_key] = self._disposal_scale_by_key[book_key]
        self._segment_start_quantity_by_key[book_key] = pool_quantity_after

    def apply_disposal(
        self,
        *,
        book_key: BookKey,
        quantity_before: Decimal,
        quantity_after: Decimal,
    ) -> None:
        if quantity_before <= Decimal(0):
            raise ValueError("AVCO source allocation requires positive quantity_before")
        if quantity_after < Decimal(0) or quantity_after > quantity_before:
            raise ValueError("AVCO source allocation quantity_after is outside the pool")

        if quantity_after.is_zero():
            self._generation_by_key[book_key] += 1
            self._disposal_scale_by_key[book_key] = Decimal(1)
            self._segment_start_scale_by_key[book_key] = Decimal(1)
            self._segment_start_quantity_by_key[book_key] = Decimal(0)
            return

        segment_start_quantity = self._segment_start_quantity_by_key[book_key]
        if segment_start_quantity <= Decimal(0):
            raise ValueError("AVCO source allocation disposal segment is not initialized")
        self._disposal_scale_by_key[book_key] = (
            self._segment_start_scale_by_key[book_key] * quantity_after / segment_start_quantity
        )

    def materialize(
        self,
        pools: Mapping[BookKey, AverageCostPool],
    ) -> dict[str, OpenLotState]:
        last_active_source_by_key: dict[BookKey, str] = {}
        for source_transaction_id, contribution in self._contributions.items():
            if contribution.generation == self._generation_by_key[contribution.book_key]:
                last_active_source_by_key[contribution.book_key] = source_transaction_id

        allocated_by_key: dict[BookKey, AverageCostPool] = defaultdict(AverageCostPool)
        states: dict[str, OpenLotState] = {}
        for source_transaction_id, contribution in self._contributions.items():
            book_key = contribution.book_key
            if contribution.generation != self._generation_by_key[book_key]:
                states[source_transaction_id] = _zero_open_lot_state()
                continue

            allocated = allocated_by_key[book_key]
            if source_transaction_id == last_active_source_by_key[book_key]:
                pool = pools[book_key]
                states[source_transaction_id] = OpenLotState(
                    quantity=pool.quantity - allocated.quantity,
                    cost_local=pool.cost_local - allocated.cost_local,
                    cost_base=pool.cost_base - allocated.cost_base,
                )
                continue

            disposal_factor = (
                self._disposal_scale_by_key[book_key] / contribution.disposal_scale_at_entry
            )
            state = OpenLotState(
                quantity=(contribution.quantity * disposal_factor).quantize(
                    LOT_QUANTITY_QUANTUM,
                    rounding=ROUND_DOWN,
                ),
                cost_local=contribution.cost_local * disposal_factor,
                cost_base=contribution.cost_base * disposal_factor,
            )
            states[source_transaction_id] = state
            allocated.add(
                quantity=state.quantity,
                cost_local=state.cost_local,
                cost_base=state.cost_base,
            )

        return states


def _zero_open_lot_state() -> OpenLotState:
    return OpenLotState(
        quantity=Decimal(0),
        cost_local=Decimal(0),
        cost_base=Decimal(0),
    )
