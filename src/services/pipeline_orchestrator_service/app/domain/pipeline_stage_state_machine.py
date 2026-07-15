"""Portfolio-day control stage policies for the surviving pipeline coordinator."""

from __future__ import annotations

FINANCIAL_RECONCILIATION_STAGE = "FINANCIAL_RECONCILIATION"
CONTROL_BLOCKING_STATUSES = frozenset({"FAILED", "REQUIRES_REPLAY"})


def is_control_stage_blocking(status: str) -> bool:
    return status in CONTROL_BLOCKING_STATUSES


def should_emit_control_stage_for_epoch(
    *,
    latest_epoch: int | None,
    event_epoch: int,
) -> bool:
    return latest_epoch is None or latest_epoch == event_epoch
