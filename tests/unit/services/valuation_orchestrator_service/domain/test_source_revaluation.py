"""Domain tests for effective-dated source revaluation scheduling."""

from datetime import date

import pytest

from src.services.valuation_orchestrator_service.app.domain.source_revaluation import (
    SourceRevaluationSchedule,
    SourceRevaluationTiming,
    decide_source_revaluation_schedule,
)

pytestmark = pytest.mark.domain


@pytest.mark.parametrize(
    ("effective_date", "latest_business_date", "expected"),
    [
        (
            date(2026, 4, 10),
            None,
            SourceRevaluationSchedule(
                timing=SourceRevaluationTiming.NO_BUSINESS_DATE,
                scan_visible_positions=False,
                stage_durable_replay=False,
            ),
        ),
        (
            date(2026, 4, 11),
            date(2026, 4, 10),
            SourceRevaluationSchedule(
                timing=SourceRevaluationTiming.FUTURE,
                scan_visible_positions=False,
                stage_durable_replay=True,
            ),
        ),
        (
            date(2026, 4, 10),
            date(2026, 4, 10),
            SourceRevaluationSchedule(
                timing=SourceRevaluationTiming.CURRENT,
                scan_visible_positions=True,
                stage_durable_replay=False,
            ),
        ),
        (
            date(2026, 4, 9),
            date(2026, 4, 10),
            SourceRevaluationSchedule(
                timing=SourceRevaluationTiming.BACKDATED,
                scan_visible_positions=True,
                stage_durable_replay=True,
            ),
        ),
    ],
)
def test_effective_dated_schedule_selects_minimum_correct_work(
    effective_date: date,
    latest_business_date: date | None,
    expected: SourceRevaluationSchedule,
) -> None:
    assert (
        decide_source_revaluation_schedule(
            effective_date=effective_date,
            latest_business_date=latest_business_date,
        )
        == expected
    )
