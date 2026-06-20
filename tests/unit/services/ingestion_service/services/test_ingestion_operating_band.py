from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.services.ingestion_operating_band import (
    OperatingBandPolicy,
    OperatingBandSignals,
    build_operating_band_policy,
    classify_operating_band,
    load_operating_band_response,
)
from src.services.ingestion_service.app.settings import IngestionOperatingBandSettings


def _policy() -> OperatingBandPolicy:
    return OperatingBandPolicy(
        yellow_backlog_age_seconds=10.0,
        orange_backlog_age_seconds=50.0,
        red_backlog_age_seconds=100.0,
        yellow_dlq_pressure_ratio=Decimal("0.20"),
        orange_dlq_pressure_ratio=Decimal("0.40"),
        red_dlq_pressure_ratio=Decimal("0.90"),
    )


def test_build_operating_band_policy_maps_runtime_settings():
    policy = build_operating_band_policy(
        IngestionOperatingBandSettings(
            yellow_backlog_age_seconds=15.0,
            orange_backlog_age_seconds=65.0,
            red_backlog_age_seconds=180.0,
            yellow_dlq_pressure_ratio=Decimal("0.25"),
            orange_dlq_pressure_ratio=Decimal("0.50"),
            red_dlq_pressure_ratio=Decimal("0.95"),
        )
    )

    assert policy == OperatingBandPolicy(
        yellow_backlog_age_seconds=15.0,
        orange_backlog_age_seconds=65.0,
        red_backlog_age_seconds=180.0,
        yellow_dlq_pressure_ratio=Decimal("0.25"),
        orange_dlq_pressure_ratio=Decimal("0.50"),
        red_dlq_pressure_ratio=Decimal("0.95"),
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


@pytest.mark.asyncio
async def test_load_operating_band_response_builds_red_response_from_runtime_loaders():
    loader_calls: list[tuple[str, dict]] = []

    async def _load_slo_status(**kwargs):
        loader_calls.append(("slo", kwargs))
        return SimpleNamespace(
            backlog_age_seconds=120.0,
            breach_failure_rate=False,
            breach_queue_latency=False,
            breach_backlog_age=True,
            failure_rate=Decimal("0.02"),
        )

    async def _load_error_budget_status(**kwargs):
        loader_calls.append(("error_budget", kwargs))
        return SimpleNamespace(dlq_pressure_ratio=Decimal("0.95"))

    response = await load_operating_band_response(
        lookback_minutes=45,
        failure_rate_threshold=Decimal("0.03"),
        queue_latency_threshold_seconds=7.5,
        backlog_age_threshold_seconds=240.0,
        policy=_policy(),
        slo_status_loader=_load_slo_status,
        error_budget_status_loader=_load_error_budget_status,
    )

    assert response.lookback_minutes == 45
    assert response.operating_band == "red"
    assert response.backlog_age_seconds == 120.0
    assert response.dlq_pressure_ratio == Decimal("0.95")
    assert response.failure_rate == Decimal("0.02")
    assert response.triggered_signals == [
        "backlog_age_seconds>=100",
        "dlq_pressure_ratio>=0.9",
    ]
    assert loader_calls == [
        (
            "slo",
            {
                "lookback_minutes": 45,
                "failure_rate_threshold": Decimal("0.03"),
                "queue_latency_threshold_seconds": 7.5,
                "backlog_age_threshold_seconds": 240.0,
            },
        ),
        (
            "error_budget",
            {
                "lookback_minutes": 45,
                "failure_rate_threshold": Decimal("0.03"),
            },
        ),
    ]
