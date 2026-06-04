from __future__ import annotations

from decimal import Decimal

from src.services.ingestion_service.app.services.ingestion_operating_band import (
    OperatingBandPolicy,
    OperatingBandSignals,
    classify_operating_band,
)


def _policy() -> OperatingBandPolicy:
    return OperatingBandPolicy(
        yellow_backlog_age_seconds=10.0,
        orange_backlog_age_seconds=50.0,
        red_backlog_age_seconds=100.0,
        yellow_dlq_pressure_ratio=Decimal("0.20"),
        orange_dlq_pressure_ratio=Decimal("0.40"),
        red_dlq_pressure_ratio=Decimal("0.90"),
    )


def _signals(
    *,
    backlog_age_seconds: float = 0.0,
    dlq_pressure_ratio: Decimal = Decimal("0.00"),
    breach_failure_rate: bool = False,
    breach_queue_latency: bool = False,
    breach_backlog_age: bool = False,
) -> OperatingBandSignals:
    return OperatingBandSignals(
        backlog_age_seconds=backlog_age_seconds,
        dlq_pressure_ratio=dlq_pressure_ratio,
        breach_failure_rate=breach_failure_rate,
        breach_queue_latency=breach_queue_latency,
        breach_backlog_age=breach_backlog_age,
        failure_rate=Decimal("0.00"),
    )


def test_classify_operating_band_returns_green_for_stable_signals():
    decision = classify_operating_band(signals=_signals(), policy=_policy())

    assert decision.operating_band == "green"
    assert decision.triggered_signals == ["stable_signals"]


def test_classify_operating_band_prioritizes_red_before_lower_bands():
    decision = classify_operating_band(
        signals=_signals(
            backlog_age_seconds=100.0,
            dlq_pressure_ratio=Decimal("1.10"),
            breach_failure_rate=True,
        ),
        policy=_policy(),
    )

    assert decision.operating_band == "red"
    assert decision.triggered_signals == [
        "backlog_age_seconds>=100",
        "dlq_pressure_ratio>=0.9",
    ]


def test_classify_operating_band_collects_orange_breach_signals():
    decision = classify_operating_band(
        signals=_signals(
            backlog_age_seconds=55.0,
            breach_failure_rate=True,
            breach_queue_latency=True,
            breach_backlog_age=True,
        ),
        policy=_policy(),
    )

    assert decision.operating_band == "orange"
    assert decision.triggered_signals == [
        "backlog_age_seconds>=50",
        "breach_failure_rate",
        "breach_queue_latency",
        "breach_backlog_age",
    ]


def test_classify_operating_band_collects_yellow_threshold_signals():
    decision = classify_operating_band(
        signals=_signals(
            backlog_age_seconds=12.0,
            dlq_pressure_ratio=Decimal("0.25"),
        ),
        policy=_policy(),
    )

    assert decision.operating_band == "yellow"
    assert decision.triggered_signals == [
        "backlog_age_seconds>=10",
        "dlq_pressure_ratio>=0.2",
    ]
