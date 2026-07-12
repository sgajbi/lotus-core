from __future__ import annotations

import pytest

from scripts.operations.transaction_processing_cutover_offsets import (
    ConsumerGroupSnapshot,
    OffsetCutoverError,
    PartitionOffset,
    build_offset_cutover_plan,
)


def _snapshot(
    group_id: str,
    *,
    offsets: tuple[int, ...] = (10, 20),
    high_watermarks: tuple[int, ...] = (10, 20),
    active_member_count: int = 0,
) -> ConsumerGroupSnapshot:
    return ConsumerGroupSnapshot(
        group_id=group_id,
        active_member_count=active_member_count,
        partitions=tuple(
            PartitionOffset(
                topic="transactions.persisted",
                partition=partition,
                committed_offset=offset,
                high_watermark=high_watermarks[partition],
            )
            for partition, offset in enumerate(offsets)
        ),
    )


def test_plan_copies_exact_drained_offsets_to_an_inactive_target() -> None:
    source = _snapshot("cost_calculator_group")
    aligned = _snapshot("cashflow_calculator_group")
    target = _snapshot("portfolio_transaction_processing_group", offsets=(-1001, -1001))

    plan = build_offset_cutover_plan(
        source=source,
        target=target,
        aligned_sources=(aligned,),
    )

    assert plan.requires_write is True
    assert plan.offsets == (("transactions.persisted", 0, 10), ("transactions.persisted", 1, 20))


def test_plan_is_idempotent_when_target_offsets_already_match() -> None:
    source = _snapshot("cost_calculator_group")

    plan = build_offset_cutover_plan(
        source=source,
        target=_snapshot("portfolio_transaction_processing_group"),
        aligned_sources=(_snapshot("cashflow_calculator_group"),),
    )

    assert plan.requires_write is False


@pytest.mark.parametrize(
    ("source", "target", "message"),
    [
        (_snapshot("source", active_member_count=1), _snapshot("target"), "source group is active"),
        (_snapshot("source"), _snapshot("target", active_member_count=1), "target group is active"),
        (
            _snapshot("source", offsets=(9, 20)),
            _snapshot("target"),
            "source group has committed lag",
        ),
    ],
)
def test_plan_rejects_unsafe_group_state(
    source: ConsumerGroupSnapshot,
    target: ConsumerGroupSnapshot,
    message: str,
) -> None:
    with pytest.raises(OffsetCutoverError, match=message):
        build_offset_cutover_plan(source=source, target=target)


def test_plan_rejects_lagging_aligned_legacy_live_group() -> None:
    with pytest.raises(OffsetCutoverError, match="source group has committed lag"):
        build_offset_cutover_plan(
            source=_snapshot("cost_calculator_group"),
            target=_snapshot("portfolio_transaction_processing_group"),
            aligned_sources=(_snapshot("cashflow_calculator_group", offsets=(10, 19)),),
        )


def test_plan_rejects_missing_source_commit() -> None:
    with pytest.raises(OffsetCutoverError, match="has no committed offset"):
        build_offset_cutover_plan(
            source=_snapshot("cost_calculator_group", offsets=(-1001, 20)),
            target=_snapshot("portfolio_transaction_processing_group"),
        )


def test_plan_can_initialize_an_empty_uncommitted_replay_partition() -> None:
    source = _snapshot(
        "cost_reprocessing_group",
        offsets=(-1001, -1001),
        high_watermarks=(0, 0),
    )

    plan = build_offset_cutover_plan(
        source=source,
        target=_snapshot(
            "portfolio_transaction_replay_request_group",
            offsets=(-1001, -1001),
            high_watermarks=(0, 0),
        ),
        allow_empty_uncommitted=True,
    )

    assert plan.offsets == (
        ("transactions.persisted", 0, 0),
        ("transactions.persisted", 1, 0),
    )
