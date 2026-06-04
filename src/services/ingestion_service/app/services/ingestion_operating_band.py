from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class OperatingBandPolicy:
    yellow_backlog_age_seconds: float
    orange_backlog_age_seconds: float
    red_backlog_age_seconds: float
    yellow_dlq_pressure_ratio: Decimal
    orange_dlq_pressure_ratio: Decimal
    red_dlq_pressure_ratio: Decimal


@dataclass(frozen=True, slots=True)
class OperatingBandSignals:
    backlog_age_seconds: float
    dlq_pressure_ratio: Decimal
    breach_failure_rate: bool
    breach_queue_latency: bool
    breach_backlog_age: bool
    failure_rate: Decimal


@dataclass(frozen=True, slots=True)
class OperatingBandDecision:
    operating_band: Literal["green", "yellow", "orange", "red"]
    recommended_action: str
    triggered_signals: list[str]


def _threshold_signal(
    *,
    metric_name: str,
    metric_value: Any,
    threshold: Any,
) -> str | None:
    if metric_value < threshold:
        return None
    if isinstance(threshold, Decimal):
        return f"{metric_name}>={threshold.normalize()}"
    return f"{metric_name}>={int(threshold)}"


def _threshold_signals(
    *,
    backlog_age_seconds: float,
    backlog_threshold_seconds: float,
    dlq_pressure_ratio: Decimal,
    dlq_pressure_threshold: Decimal,
) -> list[str]:
    signals = [
        _threshold_signal(
            metric_name="backlog_age_seconds",
            metric_value=backlog_age_seconds,
            threshold=backlog_threshold_seconds,
        ),
        _threshold_signal(
            metric_name="dlq_pressure_ratio",
            metric_value=dlq_pressure_ratio,
            threshold=dlq_pressure_threshold,
        ),
    ]
    return [signal for signal in signals if signal is not None]


def classify_operating_band(
    *,
    signals: OperatingBandSignals,
    policy: OperatingBandPolicy,
) -> OperatingBandDecision:
    red_signals = _threshold_signals(
        backlog_age_seconds=signals.backlog_age_seconds,
        backlog_threshold_seconds=policy.red_backlog_age_seconds,
        dlq_pressure_ratio=signals.dlq_pressure_ratio,
        dlq_pressure_threshold=policy.red_dlq_pressure_ratio,
    )
    if red_signals:
        return OperatingBandDecision(
            operating_band="red",
            recommended_action=(
                "Enter incident mode and block non-emergency replay until lag pressure stabilizes."
            ),
            triggered_signals=red_signals,
        )

    orange_signals = _threshold_signals(
        backlog_age_seconds=signals.backlog_age_seconds,
        backlog_threshold_seconds=policy.orange_backlog_age_seconds,
        dlq_pressure_ratio=signals.dlq_pressure_ratio,
        dlq_pressure_threshold=policy.orange_dlq_pressure_ratio,
    )
    if signals.breach_failure_rate:
        orange_signals.append("breach_failure_rate")
    if signals.breach_queue_latency:
        orange_signals.append("breach_queue_latency")
    if signals.breach_backlog_age:
        orange_signals.append("breach_backlog_age")
    if orange_signals:
        return OperatingBandDecision(
            operating_band="orange",
            recommended_action=(
                "Aggressively scale calculators and pause non-critical replay operations."
            ),
            triggered_signals=orange_signals,
        )

    yellow_signals = _threshold_signals(
        backlog_age_seconds=signals.backlog_age_seconds,
        backlog_threshold_seconds=policy.yellow_backlog_age_seconds,
        dlq_pressure_ratio=signals.dlq_pressure_ratio,
        dlq_pressure_threshold=policy.yellow_dlq_pressure_ratio,
    )
    if yellow_signals:
        return OperatingBandDecision(
            operating_band="yellow",
            recommended_action="Scale up one band and monitor DLQ pressure.",
            triggered_signals=yellow_signals,
        )

    return OperatingBandDecision(
        operating_band="green",
        recommended_action="Hold baseline replicas.",
        triggered_signals=["stable_signals"],
    )
