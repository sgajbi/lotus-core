"""Allocate average-cost source pools across linked instrument movements."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import cast

from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)

from ..average_cost_allocation_checkpoint import (
    AverageCostAllocationCheckpoint,
    AverageCostSourceAccumulator,
)
from ..average_cost_pool_checkpoint import AverageCostPoolCheckpoint
from .lot_restatement import LotRestatement
from .lot_state import OpenLotState
from .residual_allocation import allocate_nonnegative_storage_share

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
        self.quantity = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            self.quantity,
            quantity,
            field_name="pool_quantity",
        )
        self.cost_local = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            self.cost_local,
            cost_local,
            field_name="pool_cost_local",
        )
        self.cost_base = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            self.cost_base,
            cost_base,
            field_name="pool_cost_base",
        )
        self.segment_start_quantity = self.quantity
        self.segment_start_cost_local = self.cost_local
        self.segment_start_cost_base = self.cost_base

    def dispose(self, quantity: Decimal) -> tuple[Decimal, Decimal]:
        cost_local_before = self.cost_local
        cost_base_before = self.cost_base
        quantity_after = COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            self.quantity,
            quantity,
            field_name="pool_quantity",
        )
        if quantity_after.is_zero():
            self.cost_local = Decimal(0)
            self.cost_base = Decimal(0)
        else:
            with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
                remaining_cost_local = (
                    self.segment_start_cost_local * quantity_after / self.segment_start_quantity
                )
                remaining_cost_base = (
                    self.segment_start_cost_base * quantity_after / self.segment_start_quantity
                )
            self.cost_local = COST_BASIS_STATE_LEDGER_OUTPUT_V1.normalize(
                remaining_cost_local,
                field_name="pool_cost_local",
            )
            self.cost_base = COST_BASIS_STATE_LEDGER_OUTPUT_V1.normalize(
                remaining_cost_base,
                field_name="pool_cost_base",
            )
        self.quantity = quantity_after
        return (
            COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
                cost_base_before,
                self.cost_base,
                field_name="disposed_cost_base",
            ),
            COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
                cost_local_before,
                self.cost_local,
                field_name="disposed_cost_local",
            ),
        )

    def transfer_basis_out(self, *, cost_local: Decimal, cost_base: Decimal) -> None:
        self.cost_local = COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            self.cost_local,
            cost_local,
            field_name="pool_cost_local",
        )
        self.cost_base = COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            self.cost_base,
            cost_base,
            field_name="pool_cost_base",
        )
        self.segment_start_quantity = self.quantity
        self.segment_start_cost_local = self.cost_local
        self.segment_start_cost_base = self.cost_base


@dataclass(frozen=True, slots=True)
class AverageCostSourceContribution:
    book_key: BookKey
    source_lot_id: str
    source_acquisition_date: date
    generation: int
    original_quantity: Decimal
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
        self._source_ids_by_key: dict[BookKey, list[str]] = defaultdict(list)
        self._active_source_ids_by_key: dict[BookKey, list[str]] = defaultdict(list)
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
        source_lot_id: str,
        source_acquisition_date: date,
        quantity: Decimal,
        original_quantity: Decimal | None = None,
        cost_local: Decimal,
        cost_base: Decimal,
        pool_quantity_after: Decimal,
    ) -> None:
        if source_transaction_id in self._contributions:
            raise ValueError("AVCO source transaction identity must be unique")
        self._contributions[source_transaction_id] = AverageCostSourceContribution(
            book_key=book_key,
            source_lot_id=source_lot_id,
            source_acquisition_date=source_acquisition_date,
            generation=self._generation_by_key[book_key],
            original_quantity=(quantity if original_quantity is None else original_quantity),
            quantity=quantity,
            cost_local=cost_local,
            cost_base=cost_base,
            disposal_scale_at_entry=self._disposal_scale_by_key[book_key],
            cost_local_scale_at_entry=self._cost_local_scale_by_key[book_key],
            cost_base_scale_at_entry=self._cost_base_scale_by_key[book_key],
            cost_local_generation=self._cost_local_generation_by_key[book_key],
            cost_base_generation=self._cost_base_generation_by_key[book_key],
        )
        self._source_ids_by_key[book_key].append(source_transaction_id)
        self._active_source_ids_by_key[book_key].append(source_transaction_id)
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
            self._active_source_ids_by_key[book_key].clear()
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
        with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
            self._disposal_scale_by_key[book_key] = (
                self._segment_start_scale_by_key[book_key] * quantity_after / segment_start_quantity
            )

    def apply_quantity_restatement(
        self,
        *,
        book_key: BookKey,
        restatement: LotRestatement,
    ) -> None:
        """Scale every active source and segment quantity using one exact ratio."""

        proposed = {
            source_transaction_id: replace(
                self._contributions[source_transaction_id],
                original_quantity=restatement.apply(
                    self._contributions[source_transaction_id].original_quantity,
                    field_name="original_quantity",
                ),
                quantity=restatement.apply(
                    self._contributions[source_transaction_id].quantity,
                    field_name="source_quantity",
                ),
            )
            for source_transaction_id in self._active_source_ids_by_key[book_key]
        }
        segment_start_quantity = restatement.apply(
            self._segment_start_quantity_by_key[book_key],
            field_name="source_allocation_segment_start_quantity",
        )
        self._contributions.update(proposed)
        self._segment_start_quantity_by_key[book_key] = segment_start_quantity

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
        states: dict[str, OpenLotState] = {}
        for book_key in self._source_ids_by_key:
            active_states = self.materialize_book(book_key=book_key, pool=pools[book_key])
            for source_transaction_id in self._source_ids_by_key[book_key]:
                states[source_transaction_id] = active_states.get(
                    source_transaction_id,
                    OpenLotState(
                        original_quantity=self._contributions[
                            source_transaction_id
                        ].original_quantity,
                        quantity=Decimal(0),
                        cost_local=Decimal(0),
                        cost_base=Decimal(0),
                    ),
                )
        return states

    def materialize_book(
        self,
        *,
        book_key: BookKey,
        pool: AverageCostPool,
    ) -> dict[str, OpenLotState]:
        """Materialize only one book in source order for bounded disposal evidence."""

        contributions = tuple(
            (source_transaction_id, self._contributions[source_transaction_id])
            for source_transaction_id in self._active_source_ids_by_key[book_key]
        )
        allocated = AverageCostPool()
        quantities: dict[str, Decimal] = {}
        for source_transaction_id, contribution in contributions:
            disposal_factor = self._disposal_factor(contribution)
            quantity = _materialized_quantity(
                contribution=contribution,
                current_generation=self._generation_by_key[book_key],
                disposal_factor=disposal_factor,
                aggregate=pool.quantity,
                allocated=allocated.quantity,
            )
            quantities[source_transaction_id] = quantity
            allocated.quantity = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
                allocated.quantity,
                quantity,
                field_name="allocated_quantity",
            )

        _assign_quantity_residual(
            contributions=contributions,
            quantities=quantities,
            aggregate=pool.quantity,
            allocated=allocated.quantity,
        )

        last_local_cost_source_id: str | None = None
        last_base_cost_source_id: str | None = None
        for source_transaction_id, contribution in contributions:
            if quantities[source_transaction_id] <= Decimal(0):
                continue
            if contribution.cost_local_generation == self._cost_local_generation_by_key[book_key]:
                last_local_cost_source_id = source_transaction_id
            if contribution.cost_base_generation == self._cost_base_generation_by_key[book_key]:
                last_base_cost_source_id = source_transaction_id

        allocated = AverageCostPool()
        states: dict[str, OpenLotState] = {}
        for source_transaction_id, contribution in contributions:
            disposal_factor = self._disposal_factor(contribution)
            quantity = quantities[source_transaction_id]
            state = OpenLotState(
                original_quantity=contribution.original_quantity,
                quantity=quantity,
                cost_local=_materialized_cost(
                    eligible=quantity > Decimal(0),
                    source_cost=contribution.cost_local,
                    source_generation=contribution.cost_local_generation,
                    current_generation=self._cost_local_generation_by_key[book_key],
                    source_transaction_id=source_transaction_id,
                    last_source_id=last_local_cost_source_id,
                    scale=self._cost_local_scale_by_key[book_key],
                    scale_at_entry=contribution.cost_local_scale_at_entry,
                    disposal_factor=disposal_factor,
                    aggregate=pool.cost_local,
                    allocated=allocated.cost_local,
                    field_name="lot_cost_local",
                ),
                cost_base=_materialized_cost(
                    eligible=quantity > Decimal(0),
                    source_cost=contribution.cost_base,
                    source_generation=contribution.cost_base_generation,
                    current_generation=self._cost_base_generation_by_key[book_key],
                    source_transaction_id=source_transaction_id,
                    last_source_id=last_base_cost_source_id,
                    scale=self._cost_base_scale_by_key[book_key],
                    scale_at_entry=contribution.cost_base_scale_at_entry,
                    disposal_factor=disposal_factor,
                    aggregate=pool.cost_base,
                    allocated=allocated.cost_base,
                    field_name="lot_cost_base",
                ),
            )
            states[source_transaction_id] = state
            allocated.add(
                quantity=state.quantity,
                cost_local=state.cost_local,
                cost_base=state.cost_base,
            )

        return states

    def source_contributions(
        self,
        book_key: BookKey,
    ) -> tuple[tuple[str, AverageCostSourceContribution], ...]:
        """Return immutable source metadata for one book in allocation order."""

        return tuple(
            (source_transaction_id, self._contributions[source_transaction_id])
            for source_transaction_id in self._source_ids_by_key[book_key]
        )

    def active_source_contributions(
        self,
        book_key: BookKey,
    ) -> tuple[tuple[str, AverageCostSourceContribution], ...]:
        """Return only current-generation source metadata for disposal allocation."""

        return tuple(
            (source_transaction_id, self._contributions[source_transaction_id])
            for source_transaction_id in self._active_source_ids_by_key[book_key]
        )

    def export_checkpoint(
        self,
        *,
        book_key: BookKey,
        security_id: str,
        pool: AverageCostPool,
    ) -> AverageCostAllocationCheckpoint:
        """Export the exact lazy accumulator needed for deterministic ordered continuation."""

        active_sources = self.active_source_contributions(book_key)
        representative_source_transaction_id = (
            active_sources[-1][0] if pool.quantity > Decimal(0) and active_sources else None
        )
        pool_checkpoint = AverageCostPoolCheckpoint(
            portfolio_id=book_key[0],
            instrument_id=book_key[1],
            security_id=security_id,
            representative_source_transaction_id=representative_source_transaction_id,
            quantity=pool.quantity,
            cost_local=pool.cost_local,
            cost_base=pool.cost_base,
        )
        is_closed = pool.quantity.is_zero()
        return AverageCostAllocationCheckpoint(
            pool=pool_checkpoint,
            segment_start_quantity=(Decimal(0) if is_closed else pool.segment_start_quantity),
            segment_start_cost_local=(Decimal(0) if is_closed else pool.segment_start_cost_local),
            segment_start_cost_base=(Decimal(0) if is_closed else pool.segment_start_cost_base),
            source_allocation_segment_start_quantity=(
                Decimal(0) if is_closed else self._segment_start_quantity_by_key[book_key]
            ),
            allocation_generation=self._generation_by_key[book_key],
            disposal_scale=self._disposal_scale_by_key[book_key],
            segment_start_scale=self._segment_start_scale_by_key[book_key],
            cost_local_scale=self._cost_local_scale_by_key[book_key],
            cost_base_scale=self._cost_base_scale_by_key[book_key],
            cost_local_generation=self._cost_local_generation_by_key[book_key],
            cost_base_generation=self._cost_base_generation_by_key[book_key],
            sources=tuple(
                AverageCostSourceAccumulator(
                    source_transaction_id=source_transaction_id,
                    source_lot_id=contribution.source_lot_id,
                    source_acquisition_date=contribution.source_acquisition_date,
                    source_sequence=source_sequence,
                    generation=contribution.generation,
                    original_quantity=contribution.original_quantity,
                    quantity=contribution.quantity,
                    cost_local=contribution.cost_local,
                    cost_base=contribution.cost_base,
                    disposal_scale_at_entry=contribution.disposal_scale_at_entry,
                    cost_local_scale_at_entry=contribution.cost_local_scale_at_entry,
                    cost_base_scale_at_entry=contribution.cost_base_scale_at_entry,
                    cost_local_generation=contribution.cost_local_generation,
                    cost_base_generation=contribution.cost_base_generation,
                )
                for source_sequence, (source_transaction_id, contribution) in enumerate(
                    active_sources,
                    start=1,
                )
            ),
        )

    def restore_checkpoint(
        self,
        checkpoint: AverageCostAllocationCheckpoint,
    ) -> AverageCostPool:
        """Restore one validated checkpoint into an otherwise empty allocation engine."""

        if self._contributions:
            raise ValueError("AVCO source-allocation restore requires an empty engine")
        book_key = (checkpoint.pool.portfolio_id, checkpoint.pool.instrument_id)
        if book_key in self._source_ids_by_key or book_key in self._active_source_ids_by_key:
            raise ValueError("AVCO source-allocation checkpoint book already exists")

        source_ids: list[str] = []
        for source in checkpoint.sources:
            self._contributions[source.source_transaction_id] = AverageCostSourceContribution(
                book_key=book_key,
                source_lot_id=source.source_lot_id,
                source_acquisition_date=source.source_acquisition_date,
                generation=source.generation,
                original_quantity=source.original_quantity,
                quantity=source.quantity,
                cost_local=source.cost_local,
                cost_base=source.cost_base,
                disposal_scale_at_entry=source.disposal_scale_at_entry,
                cost_local_scale_at_entry=source.cost_local_scale_at_entry,
                cost_base_scale_at_entry=source.cost_base_scale_at_entry,
                cost_local_generation=source.cost_local_generation,
                cost_base_generation=source.cost_base_generation,
            )
            source_ids.append(source.source_transaction_id)
        self._source_ids_by_key[book_key] = list(source_ids)
        self._active_source_ids_by_key[book_key] = list(source_ids)
        self._generation_by_key[book_key] = checkpoint.allocation_generation
        self._disposal_scale_by_key[book_key] = checkpoint.disposal_scale
        self._segment_start_scale_by_key[book_key] = checkpoint.segment_start_scale
        self._segment_start_quantity_by_key[book_key] = (
            checkpoint.source_allocation_segment_start_quantity
        )
        self._cost_local_scale_by_key[book_key] = checkpoint.cost_local_scale
        self._cost_base_scale_by_key[book_key] = checkpoint.cost_base_scale
        self._cost_local_generation_by_key[book_key] = checkpoint.cost_local_generation
        self._cost_base_generation_by_key[book_key] = checkpoint.cost_base_generation
        return AverageCostPool(
            quantity=checkpoint.pool.quantity,
            cost_local=checkpoint.pool.cost_local,
            cost_base=checkpoint.pool.cost_base,
            segment_start_quantity=checkpoint.segment_start_quantity,
            segment_start_cost_local=checkpoint.segment_start_cost_local,
            segment_start_cost_base=checkpoint.segment_start_cost_base,
        )

    def _disposal_factor(self, contribution: AverageCostSourceContribution) -> Decimal:
        if contribution.generation != self._generation_by_key[contribution.book_key]:
            return Decimal(0)
        with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
            return (
                self._disposal_scale_by_key[contribution.book_key]
                / contribution.disposal_scale_at_entry
            )


def _materialized_quantity(
    *,
    contribution: AverageCostSourceContribution,
    current_generation: int,
    disposal_factor: Decimal,
    aggregate: Decimal,
    allocated: Decimal,
) -> Decimal:
    if contribution.generation != current_generation:
        return Decimal(0)
    with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
        quantity = (contribution.quantity * disposal_factor).quantize(
            LOT_QUANTITY_QUANTUM,
            rounding=ROUND_DOWN,
        )
    bounded_share = cast(
        Decimal,
        allocate_nonnegative_storage_share(
            quantity,
            aggregate=aggregate,
            allocated=allocated,
            field_name="open_quantity",
        ),
    )
    return min(bounded_share, contribution.original_quantity)


def _assign_quantity_residual(
    *,
    contributions: tuple[tuple[str, AverageCostSourceContribution], ...],
    quantities: dict[str, Decimal],
    aggregate: Decimal,
    allocated: Decimal,
) -> None:
    """Assign rounding residual without exceeding any source lot's authority."""

    remaining = cast(
        Decimal,
        COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            aggregate,
            allocated,
            field_name="unallocated_open_quantity",
        ),
    )
    for source_transaction_id, contribution in reversed(contributions):
        if remaining == Decimal(0):
            return
        current = quantities[source_transaction_id]
        headroom = cast(
            Decimal,
            COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
                contribution.original_quantity,
                current,
                field_name="source_quantity_headroom",
            ),
        )
        assigned = min(remaining, headroom)
        quantities[source_transaction_id] = cast(
            Decimal,
            COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
                current,
                assigned,
                field_name="open_quantity",
            ),
        )
        remaining = cast(
            Decimal,
            COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
                remaining,
                assigned,
                field_name="unallocated_open_quantity",
            ),
        )
    if remaining != Decimal(0):
        raise ValueError("AVCO pool quantity exceeds source original quantity authority")


def _materialized_cost(
    *,
    eligible: bool,
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
    field_name: str,
) -> Decimal:
    if not eligible or source_generation != current_generation:
        return Decimal(0)
    if source_transaction_id == last_source_id:
        return cast(
            Decimal,
            COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
                aggregate,
                allocated,
                field_name=field_name,
            ),
        )
    with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
        materialized_cost = source_cost * disposal_factor * scale / scale_at_entry
    return cast(
        Decimal,
        allocate_nonnegative_storage_share(
            materialized_cost,
            aggregate=aggregate,
            allocated=allocated,
            field_name=field_name,
        ),
    )


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
    with COST_BASIS_STATE_LEDGER_OUTPUT_V1.arithmetic_context():
        return current_scale * cost_after / cost_before
