"""Prove the persisted AVCO source-allocation checkpoint contract."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AVERAGE_COST_ALLOCATION_STATE_VERSION,
    AverageCostAllocationCheckpoint,
    AverageCostPoolCheckpoint,
    AverageCostSourceAccumulator,
)


def _source(
    source_transaction_id: str = "BUY-1",
    *,
    source_sequence: int = 1,
) -> AverageCostSourceAccumulator:
    return AverageCostSourceAccumulator(
        source_transaction_id=source_transaction_id,
        source_lot_id=f"LOT-{source_transaction_id}",
        source_acquisition_date=date(2026, 1, source_sequence),
        source_sequence=source_sequence,
        generation=2,
        original_quantity=Decimal("10"),
        quantity=Decimal("10"),
        cost_local=Decimal("98"),
        cost_base=Decimal("100"),
        disposal_scale_at_entry=Decimal("0.75"),
        cost_local_scale_at_entry=Decimal("1"),
        cost_base_scale_at_entry=Decimal("1"),
        cost_local_generation=1,
        cost_base_generation=1,
    )


def _open_checkpoint() -> AverageCostAllocationCheckpoint:
    return AverageCostAllocationCheckpoint(
        pool=AverageCostPoolCheckpoint(
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            representative_source_transaction_id="BUY-2",
            quantity=Decimal("20"),
            cost_local=Decimal("196"),
            cost_base=Decimal("200"),
        ),
        segment_start_quantity=Decimal("24"),
        segment_start_cost_local=Decimal("235.2"),
        segment_start_cost_base=Decimal("240"),
        source_allocation_segment_start_quantity=Decimal("24"),
        allocation_generation=2,
        disposal_scale=Decimal("0.75"),
        segment_start_scale=Decimal("0.9"),
        cost_local_scale=Decimal("1"),
        cost_base_scale=Decimal("1"),
        cost_local_generation=1,
        cost_base_generation=1,
        sources=(
            _source(),
            _source("BUY-2", source_sequence=2),
        ),
    )


def test_open_checkpoint_binds_pool_and_ordered_active_sources() -> None:
    checkpoint = _open_checkpoint()

    assert checkpoint.state_version == AVERAGE_COST_ALLOCATION_STATE_VERSION
    assert [source.source_transaction_id for source in checkpoint.sources] == ["BUY-1", "BUY-2"]
    assert checkpoint.pool.representative_source_transaction_id == "BUY-2"


def test_open_checkpoint_allows_quantity_sources_from_prior_cost_generation() -> None:
    checkpoint = _open_checkpoint()

    restored = replace(
        checkpoint,
        pool=replace(
            checkpoint.pool,
            cost_local=Decimal("98"),
            cost_base=Decimal("100"),
        ),
        segment_start_quantity=Decimal("20"),
        segment_start_cost_local=Decimal("98"),
        segment_start_cost_base=Decimal("100"),
        sources=(
            replace(
                checkpoint.sources[0],
                cost_local_generation=0,
                cost_base_generation=0,
            ),
            checkpoint.sources[1],
        ),
    )

    assert restored.sources[0].cost_local_generation == 0
    assert restored.sources[0].cost_base_generation == 0


def test_open_checkpoint_rejects_disposal_scale_inconsistent_with_source_segment() -> None:
    checkpoint = _open_checkpoint()

    with pytest.raises(ValueError, match="disposal scale conflicts"):
        replace(checkpoint, disposal_scale=checkpoint.disposal_scale * Decimal(2))


def test_open_checkpoint_rejects_source_cost_inconsistent_with_pool() -> None:
    checkpoint = _open_checkpoint()

    with pytest.raises(ValueError, match="accumulators conflict"):
        replace(
            checkpoint,
            sources=(
                replace(checkpoint.sources[0], cost_base=Decimal("101")),
                checkpoint.sources[1],
            ),
        )


def test_open_checkpoint_rejects_pool_cost_inconsistent_with_disposal_segment() -> None:
    checkpoint = _open_checkpoint()

    with pytest.raises(ValueError, match="pool costs conflict"):
        replace(
            checkpoint,
            segment_start_cost_local=Decimal("90"),
            segment_start_cost_base=Decimal("90"),
        )


def test_closed_checkpoint_requires_zero_segment_and_no_sources() -> None:
    checkpoint = AverageCostAllocationCheckpoint(
        pool=AverageCostPoolCheckpoint(
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            representative_source_transaction_id=None,
            quantity=Decimal(0),
            cost_local=Decimal(0),
            cost_base=Decimal(0),
        ),
        segment_start_quantity=Decimal(0),
        segment_start_cost_local=Decimal(0),
        segment_start_cost_base=Decimal(0),
        source_allocation_segment_start_quantity=Decimal(0),
        allocation_generation=3,
        disposal_scale=Decimal(1),
        segment_start_scale=Decimal(1),
        cost_local_scale=Decimal(1),
        cost_base_scale=Decimal(1),
        cost_local_generation=2,
        cost_base_generation=2,
        sources=(),
    )

    assert checkpoint.sources == ()


@pytest.mark.parametrize(
    "mutator, expected",
    [
        (lambda value: replace(value, sources=()), "requires active source"),
        (
            lambda value: replace(value, sources=(value.sources[0], value.sources[0])),
            "identities must be unique",
        ),
        (
            lambda value: replace(
                value,
                sources=(value.sources[0], replace(value.sources[1], source_sequence=3)),
            ),
            "sequences must be contiguous",
        ),
        (
            lambda value: replace(
                value,
                sources=(replace(value.sources[0], generation=1), value.sources[1]),
            ),
            "match the allocation generation",
        ),
        (
            lambda value: replace(
                value,
                sources=(
                    replace(value.sources[0], cost_local_generation=2),
                    value.sources[1],
                ),
            ),
            "generation cannot be in the future",
        ),
        (
            lambda value: replace(
                value,
                pool=replace(value.pool, representative_source_transaction_id="BUY-3"),
            ),
            "representative source is absent",
        ),
    ],
)
def test_checkpoint_rejects_incomplete_or_conflicting_source_state(
    mutator: Callable[[AverageCostAllocationCheckpoint], AverageCostAllocationCheckpoint],
    expected: str,
) -> None:
    with pytest.raises(ValueError, match=expected):
        mutator(_open_checkpoint())


@pytest.mark.parametrize(
    "field_name, value, error",
    [
        ("source_transaction_id", " ", "must be nonblank"),
        ("source_lot_id", 1, "must be a string"),
        ("source_acquisition_date", datetime(2026, 1, 1), "must be a date"),
        ("source_sequence", True, "must be an integer"),
        ("generation", -1, "must be nonnegative"),
        ("quantity", Decimal(0), "must be positive"),
        ("cost_local", Decimal("NaN"), "must be finite"),
        ("disposal_scale_at_entry", Decimal(0), "must be positive"),
    ],
)
def test_source_accumulator_rejects_malformed_identity_and_numeric_state(
    field_name: str,
    value: object,
    error: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=error):
        replace(_source(), **{field_name: value})


def test_checkpoint_rejects_active_sources_after_pool_close() -> None:
    open_checkpoint = _open_checkpoint()
    closed_pool = AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id=None,
        quantity=Decimal(0),
        cost_local=Decimal(0),
        cost_base=Decimal(0),
    )

    with pytest.raises(ValueError, match="cannot retain active sources"):
        replace(
            open_checkpoint,
            pool=closed_pool,
            segment_start_quantity=Decimal(0),
            segment_start_cost_local=Decimal(0),
            segment_start_cost_base=Decimal(0),
        )
