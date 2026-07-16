"""Decide bounded revaluation work for effective-dated source observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class SourceRevaluationTiming(StrEnum):
    """Classify one source observation against the governed valuation horizon."""

    NO_BUSINESS_DATE = "NO_BUSINESS_DATE"
    FUTURE = "FUTURE"
    CURRENT = "CURRENT"
    BACKDATED = "BACKDATED"


@dataclass(frozen=True, slots=True)
class SourceRevaluationSchedule:
    """Describe immediate and durable work without infrastructure concepts."""

    timing: SourceRevaluationTiming
    scan_visible_positions: bool
    stage_durable_replay: bool


def decide_source_revaluation_schedule(
    *,
    effective_date: date,
    latest_business_date: date | None,
) -> SourceRevaluationSchedule:
    """
    Select the minimum work that preserves effective-dated valuation correctness.

    Current-date observations do not need replay for positions that do not exist yet:
    the transaction-owned valuation-readiness event will value every later position
    against the already committed source fact. Backdated and future observations retain
    durable replay because they can affect state outside that immediate readiness path.
    """

    if latest_business_date is None:
        return SourceRevaluationSchedule(
            timing=SourceRevaluationTiming.NO_BUSINESS_DATE,
            scan_visible_positions=False,
            stage_durable_replay=True,
        )
    if effective_date > latest_business_date:
        return SourceRevaluationSchedule(
            timing=SourceRevaluationTiming.FUTURE,
            scan_visible_positions=False,
            stage_durable_replay=True,
        )
    if effective_date < latest_business_date:
        return SourceRevaluationSchedule(
            timing=SourceRevaluationTiming.BACKDATED,
            scan_visible_positions=True,
            stage_durable_replay=True,
        )
    return SourceRevaluationSchedule(
        timing=SourceRevaluationTiming.CURRENT,
        scan_visible_positions=True,
        stage_durable_replay=False,
    )
