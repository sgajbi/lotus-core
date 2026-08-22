"""Define the persisted AVCO source-allocation accumulator contract."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from decimal import Context, Decimal, localcontext
from typing import cast

from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)

from .average_cost_pool_checkpoint import AverageCostPoolCheckpoint

AVERAGE_COST_ALLOCATION_STATE_VERSION = "avco-source-allocation-v1"


@dataclass(frozen=True, slots=True)
class AverageCostSourceAccumulator:
    """Persist one active source contribution without materializing every disposal."""

    source_transaction_id: str
    source_lot_id: str
    source_acquisition_date: date
    source_sequence: int
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

    def __post_init__(self) -> None:
        for field_name in ("source_transaction_id", "source_lot_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        if type(self.source_acquisition_date) is not date:
            raise TypeError("source_acquisition_date must be a date")
        _require_nonnegative_integer(self.source_sequence, field_name="source_sequence")
        if self.source_sequence < 1:
            raise ValueError("source_sequence must be positive")
        for field_name in ("generation", "cost_local_generation", "cost_base_generation"):
            _require_nonnegative_integer(getattr(self, field_name), field_name=field_name)
        for field_name in ("original_quantity", "quantity", "cost_local", "cost_base"):
            _require_decimal(getattr(self, field_name), field_name=field_name, positive=False)
        if self.quantity > self.original_quantity:
            raise ValueError("AVCO source quantity must not exceed original_quantity")
        if self.quantity == Decimal(0):
            raise ValueError("active AVCO source quantity must be positive")
        for field_name in (
            "disposal_scale_at_entry",
            "cost_local_scale_at_entry",
            "cost_base_scale_at_entry",
        ):
            _require_decimal(getattr(self, field_name), field_name=field_name, positive=True)


@dataclass(frozen=True, slots=True)
class AverageCostAllocationCheckpoint:
    """Bind an aggregate pool to the exact lazy source-allocation accumulator."""

    pool: AverageCostPoolCheckpoint
    segment_start_quantity: Decimal
    segment_start_cost_local: Decimal
    segment_start_cost_base: Decimal
    source_allocation_segment_start_quantity: Decimal
    allocation_generation: int
    disposal_scale: Decimal
    segment_start_scale: Decimal
    cost_local_scale: Decimal
    cost_base_scale: Decimal
    cost_local_generation: int
    cost_base_generation: int
    sources: tuple[AverageCostSourceAccumulator, ...]
    state_version: str = AVERAGE_COST_ALLOCATION_STATE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.pool, AverageCostPoolCheckpoint):
            raise TypeError("pool must be an AverageCostPoolCheckpoint")
        for field_name in (
            "segment_start_quantity",
            "segment_start_cost_local",
            "segment_start_cost_base",
            "source_allocation_segment_start_quantity",
        ):
            _require_decimal(getattr(self, field_name), field_name=field_name, positive=False)
        for field_name in (
            "allocation_generation",
            "cost_local_generation",
            "cost_base_generation",
        ):
            _require_nonnegative_integer(getattr(self, field_name), field_name=field_name)
        for field_name in (
            "disposal_scale",
            "segment_start_scale",
            "cost_local_scale",
            "cost_base_scale",
        ):
            _require_decimal(getattr(self, field_name), field_name=field_name, positive=True)
        if not isinstance(self.sources, tuple) or not all(
            isinstance(source, AverageCostSourceAccumulator) for source in self.sources
        ):
            raise TypeError("sources must be a tuple of AverageCostSourceAccumulator")
        if self.state_version != AVERAGE_COST_ALLOCATION_STATE_VERSION:
            raise ValueError("unsupported AVCO source-allocation checkpoint version")

        source_ids = tuple(source.source_transaction_id for source in self.sources)
        source_lot_ids = tuple(source.source_lot_id for source in self.sources)
        if len(set(source_ids)) != len(source_ids) or len(set(source_lot_ids)) != len(
            source_lot_ids
        ):
            raise ValueError("AVCO source-allocation identities must be unique")
        if tuple(source.source_sequence for source in self.sources) != tuple(
            range(1, len(self.sources) + 1)
        ):
            raise ValueError("AVCO source sequences must be contiguous from one")
        if any(source.generation != self.allocation_generation for source in self.sources):
            raise ValueError("active AVCO sources must match the allocation generation")
        if any(
            source.cost_local_generation > self.cost_local_generation
            or source.cost_base_generation > self.cost_base_generation
            for source in self.sources
        ):
            raise ValueError("active AVCO source cost generation cannot be in the future")

        if self.pool.quantity == Decimal(0):
            if self.sources:
                raise ValueError("closed AVCO checkpoint cannot retain active sources")
            if any(
                (
                    self.segment_start_quantity,
                    self.segment_start_cost_local,
                    self.segment_start_cost_base,
                    self.source_allocation_segment_start_quantity,
                )
            ):
                raise ValueError("closed AVCO checkpoint must have zero segment state")
            return
        if not self.sources:
            raise ValueError("open AVCO checkpoint requires active source accumulators")
        if self.pool.representative_source_transaction_id not in source_ids:
            raise ValueError("AVCO representative source is absent from the accumulator")
        if self.segment_start_quantity <= Decimal(0):
            raise ValueError("open AVCO checkpoint requires positive segment quantity")
        if self.source_allocation_segment_start_quantity <= Decimal(0):
            raise ValueError("open AVCO checkpoint requires positive source-allocation segment")
        self._validate_materialized_totals()

    def _validate_materialized_totals(self) -> None:
        with _checkpoint_arithmetic_context():
            expected_disposal_scale = (
                self.segment_start_scale
                * self.pool.quantity
                / self.source_allocation_segment_start_quantity
            )
        if _normalize_checkpoint_value(
            expected_disposal_scale,
            field_name="disposal_scale",
        ) != _normalize_checkpoint_value(self.disposal_scale, field_name="disposal_scale"):
            raise ValueError("AVCO disposal scale conflicts with source-allocation segment")
        if self.pool.quantity > self.segment_start_quantity:
            raise ValueError("AVCO pool quantity exceeds its disposal segment")
        with _checkpoint_arithmetic_context():
            expected_pool_cost_local = (
                self.segment_start_cost_local * self.pool.quantity / self.segment_start_quantity
            )
            expected_pool_cost_base = (
                self.segment_start_cost_base * self.pool.quantity / self.segment_start_quantity
            )
        if (
            _normalize_checkpoint_value(
                expected_pool_cost_local,
                field_name="pool_cost_local",
            )
            != self.pool.cost_local
            or _normalize_checkpoint_value(
                expected_pool_cost_base,
                field_name="pool_cost_base",
            )
            != self.pool.cost_base
        ):
            raise ValueError("AVCO pool costs conflict with disposal segment state")

        expected_quantity = _materialized_total(
            self,
            value_field="quantity",
            scale_field=None,
            scale_at_entry_field=None,
            generation_field=None,
            current_generation=None,
            output_field="open_quantity",
        )
        expected_cost_local = _materialized_total(
            self,
            value_field="cost_local",
            scale_field="cost_local_scale",
            scale_at_entry_field="cost_local_scale_at_entry",
            generation_field="cost_local_generation",
            current_generation=self.cost_local_generation,
            output_field="lot_cost_local",
        )
        expected_cost_base = _materialized_total(
            self,
            value_field="cost_base",
            scale_field="cost_base_scale",
            scale_at_entry_field="cost_base_scale_at_entry",
            generation_field="cost_base_generation",
            current_generation=self.cost_base_generation,
            output_field="lot_cost_base",
        )
        if (
            expected_quantity != self.pool.quantity
            or expected_cost_local != self.pool.cost_local
            or expected_cost_base != self.pool.cost_base
        ):
            raise ValueError("AVCO source accumulators conflict with aggregate pool state")


def _require_decimal(value: object, *, field_name: str, positive: bool) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < Decimal(0) or (positive and value == Decimal(0)):
        requirement = "positive" if positive else "nonnegative"
        raise ValueError(f"{field_name} must be {requirement}")


def _materialized_total(
    checkpoint: AverageCostAllocationCheckpoint,
    *,
    value_field: str,
    scale_field: str | None,
    scale_at_entry_field: str | None,
    generation_field: str | None,
    current_generation: int | None,
    output_field: str,
) -> Decimal:
    total = Decimal(0)
    with _checkpoint_arithmetic_context():
        for source in checkpoint.sources:
            if generation_field is not None and (
                getattr(source, generation_field) != current_generation
            ):
                continue
            materialized = (
                cast(Decimal, getattr(source, value_field))
                * checkpoint.disposal_scale
                / source.disposal_scale_at_entry
            )
            if scale_field is not None and scale_at_entry_field is not None:
                materialized = (
                    materialized
                    * cast(Decimal, getattr(checkpoint, scale_field))
                    / cast(Decimal, getattr(source, scale_at_entry_field))
                )
            total += materialized
    return _normalize_checkpoint_value(total, field_name=output_field)


def _checkpoint_arithmetic_context() -> AbstractContextManager[Context]:
    return localcontext(
        Context(
            prec=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
            rounding=COST_BASIS_STATE_LEDGER_OUTPUT_V1.rounding,
        )
    )


def _normalize_checkpoint_value(value: Decimal, *, field_name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{field_name} checkpoint total must be finite")
    quantum = Decimal(1).scaleb(-COST_BASIS_STATE_LEDGER_OUTPUT_V1.scale)
    with _checkpoint_arithmetic_context():
        return value.quantize(
            quantum,
            rounding=COST_BASIS_STATE_LEDGER_OUTPUT_V1.rounding,
        )


def _require_nonnegative_integer(value: object, *, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative")
