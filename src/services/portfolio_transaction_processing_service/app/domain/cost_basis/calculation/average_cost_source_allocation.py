"""Allocate average-cost source pools across linked instrument movements."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from .lot_state import OpenLotState

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

    def transfer_basis_out(self, *, cost_local: Decimal, cost_base: Decimal) -> None:
        self.cost_local -= cost_local
        self.cost_base -= cost_base
        self.segment_start_quantity = self.quantity
        self.segment_start_cost_local = self.cost_local
        self.segment_start_cost_base = self.cost_base


@dataclass(frozen=True, slots=True)
class AverageCostSourceContribution:
    book_key: BookKey
    generation: int
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal
    disposal_scale_at_entry: Decimal
    cost_local_scale_at_entry: Decimal
    cost_base_scale_at_entry: Decimal
    cost_local_generation: int
    cost_base_generation: int


class AverageCostSourceAllocation:
    """Lazily scale AVCO source contributions and materialize exact aggregate state once."""

    def __init__(self) -> None:
        self._contributions: dict[str, AverageCostSourceContribution] = {}
        self._generation_by_key: dict[BookKey, int] = defaultdict(int)
        self._disposal_scale_by_key: dict[BookKey, Decimal] = defaultdict(lambda: Decimal(1))
        self._segment_start_scale_by_key: dict[BookKey, Decimal] = defaultdict(lambda: Decimal(1))
        self._segment_start_quantity_by_key: dict[BookKey, Decimal] = defaultdict(Decimal)
        self._cost_local_scale_by_key: dict[BookKey, Decimal] = defaultdict(lambda: Decimal(1))
        self._cost_base_scale_by_key: dict[BookKey, Decimal] = defaultdict(lambda: Decimal(1))
        self._cost_local_generation_by_key: dict[BookKey, int] = defaultdict(int)
        self._cost_base_generation_by_key: dict[BookKey, int] = defaultdict(int)

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
            cost_local_scale_at_entry=self._cost_local_scale_by_key[book_key],
            cost_base_scale_at_entry=self._cost_base_scale_by_key[book_key],
            cost_local_generation=self._cost_local_generation_by_key[book_key],
            cost_base_generation=self._cost_base_generation_by_key[book_key],
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
            self._cost_local_scale_by_key[book_key] = Decimal(1)
            self._cost_base_scale_by_key[book_key] = Decimal(1)
            self._cost_local_generation_by_key[book_key] += 1
            self._cost_base_generation_by_key[book_key] += 1
            return

        segment_start_quantity = self._segment_start_quantity_by_key[book_key]
        if segment_start_quantity <= Decimal(0):
            raise ValueError("AVCO source allocation disposal segment is not initialized")
        self._disposal_scale_by_key[book_key] = (
            self._segment_start_scale_by_key[book_key] * quantity_after / segment_start_quantity
        )

    def apply_basis_transfer(
        self,
        *,
        book_key: BookKey,
        cost_local_before: Decimal,
        cost_local_after: Decimal,
        cost_base_before: Decimal,
        cost_base_after: Decimal,
    ) -> None:
        local_scale = _scaled_basis_factor(
            current_scale=self._cost_local_scale_by_key[book_key],
            cost_before=cost_local_before,
            cost_after=cost_local_after,
            currency_basis="local",
        )
        base_scale = _scaled_basis_factor(
            current_scale=self._cost_base_scale_by_key[book_key],
            cost_before=cost_base_before,
            cost_after=cost_base_after,
            currency_basis="base",
        )
        self._cost_local_scale_by_key[book_key] = local_scale or Decimal(1)
        self._cost_base_scale_by_key[book_key] = base_scale or Decimal(1)
        if local_scale.is_zero():
            self._cost_local_generation_by_key[book_key] += 1
        if base_scale.is_zero():
            self._cost_base_generation_by_key[book_key] += 1

    def materialize(
        self,
        pools: Mapping[BookKey, AverageCostPool],
    ) -> dict[str, OpenLotState]:
        last_quantity_source_by_key: dict[BookKey, str] = {}
        last_local_cost_source_by_key: dict[BookKey, str] = {}
        last_base_cost_source_by_key: dict[BookKey, str] = {}
        for source_transaction_id, contribution in self._contributions.items():
            if contribution.generation == self._generation_by_key[contribution.book_key]:
                last_quantity_source_by_key[contribution.book_key] = source_transaction_id
            if (
                contribution.cost_local_generation
                == self._cost_local_generation_by_key[contribution.book_key]
            ):
                last_local_cost_source_by_key[contribution.book_key] = source_transaction_id
            if (
                contribution.cost_base_generation
                == self._cost_base_generation_by_key[contribution.book_key]
            ):
                last_base_cost_source_by_key[contribution.book_key] = source_transaction_id

        allocated_by_key: dict[BookKey, AverageCostPool] = defaultdict(AverageCostPool)
        states: dict[str, OpenLotState] = {}
        for source_transaction_id, contribution in self._contributions.items():
            book_key = contribution.book_key
            allocated = allocated_by_key[book_key]
            pool = pools[book_key]
            disposal_factor = self._disposal_factor(contribution)
            state = OpenLotState(
                quantity=_materialized_quantity(
                    contribution=contribution,
                    source_transaction_id=source_transaction_id,
                    current_generation=self._generation_by_key[book_key],
                    last_source_id=last_quantity_source_by_key.get(book_key),
                    disposal_factor=disposal_factor,
                    aggregate=pool.quantity,
                    allocated=allocated.quantity,
                ),
                cost_local=_materialized_cost(
                    source_cost=contribution.cost_local,
                    source_generation=contribution.cost_local_generation,
                    current_generation=self._cost_local_generation_by_key[book_key],
                    source_transaction_id=source_transaction_id,
                    last_source_id=last_local_cost_source_by_key.get(book_key),
                    scale=self._cost_local_scale_by_key[book_key],
                    scale_at_entry=contribution.cost_local_scale_at_entry,
                    disposal_factor=disposal_factor,
                    aggregate=pool.cost_local,
                    allocated=allocated.cost_local,
                ),
                cost_base=_materialized_cost(
                    source_cost=contribution.cost_base,
                    source_generation=contribution.cost_base_generation,
                    current_generation=self._cost_base_generation_by_key[book_key],
                    source_transaction_id=source_transaction_id,
                    last_source_id=last_base_cost_source_by_key.get(book_key),
                    scale=self._cost_base_scale_by_key[book_key],
                    scale_at_entry=contribution.cost_base_scale_at_entry,
                    disposal_factor=disposal_factor,
                    aggregate=pool.cost_base,
                    allocated=allocated.cost_base,
                ),
            )
            states[source_transaction_id] = state
            allocated.add(
                quantity=state.quantity,
                cost_local=state.cost_local,
                cost_base=state.cost_base,
            )

        return states

    def _disposal_factor(self, contribution: AverageCostSourceContribution) -> Decimal:
        if contribution.generation != self._generation_by_key[contribution.book_key]:
            return Decimal(0)
        return (
            self._disposal_scale_by_key[contribution.book_key]
            / contribution.disposal_scale_at_entry
        )


def _materialized_quantity(
    *,
    contribution: AverageCostSourceContribution,
    source_transaction_id: str,
    current_generation: int,
    last_source_id: str | None,
    disposal_factor: Decimal,
    aggregate: Decimal,
    allocated: Decimal,
) -> Decimal:
    if contribution.generation != current_generation:
        return Decimal(0)
    if source_transaction_id == last_source_id:
        return aggregate - allocated
    return (contribution.quantity * disposal_factor).quantize(
        LOT_QUANTITY_QUANTUM,
        rounding=ROUND_DOWN,
    )


def _materialized_cost(
    *,
    source_cost: Decimal,
    source_generation: int,
    current_generation: int,
    source_transaction_id: str,
    last_source_id: str | None,
    scale: Decimal,
    scale_at_entry: Decimal,
    disposal_factor: Decimal,
    aggregate: Decimal,
    allocated: Decimal,
) -> Decimal:
    if source_generation != current_generation:
        return Decimal(0)
    if source_transaction_id == last_source_id:
        return aggregate - allocated
    return source_cost * disposal_factor * scale / scale_at_entry


def _scaled_basis_factor(
    *,
    current_scale: Decimal,
    cost_before: Decimal,
    cost_after: Decimal,
    currency_basis: str,
) -> Decimal:
    if cost_before <= Decimal(0):
        raise ValueError(f"AVCO {currency_basis} cost basis must be positive before transfer")
    if cost_after < Decimal(0) or cost_after > cost_before:
        raise ValueError(f"AVCO {currency_basis} cost basis after transfer is invalid")
    return current_scale * cost_after / cost_before
