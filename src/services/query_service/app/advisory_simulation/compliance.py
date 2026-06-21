"""
FILE: src/core/compliance.py
Post-trade Rule Engine implementation (RFC-0005/RFC-0006B).
"""

from decimal import Decimal
from typing import List

from src.services.query_service.app.advisory_simulation.models import (
    DiagnosticsData,
    EngineOptions,
    RuleResult,
    SimulatedState,
)

_ZERO = Decimal("0")
_SINGLE_POSITION_TOLERANCE = Decimal("0.001")


def _result(
    *,
    rule_id: str,
    severity: str,
    status: str,
    measured: Decimal,
    threshold: dict[str, Decimal],
    reason_code: str,
    remediation_hint: str | None = None,
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        severity=severity,
        status=status,
        measured=measured,
        threshold=threshold,
        reason_code=reason_code,
        remediation_hint=remediation_hint,
    )


def _cash_weight(state: SimulatedState) -> Decimal:
    return next(
        (a.weight for a in state.allocation_by_asset_class if a.key == "CASH"),
        _ZERO,
    )


def _cash_band_result(state: SimulatedState, options: EngineOptions) -> RuleResult:
    cash_weight = _cash_weight(state)
    min_w = options.cash_band_min_weight
    max_w = options.cash_band_max_weight
    breached = cash_weight < min_w or cash_weight > max_w
    return _result(
        rule_id="CASH_BAND",
        severity="SOFT",
        status="FAIL" if breached else "PASS",
        measured=cash_weight,
        threshold={"min": min_w, "max": max_w},
        reason_code="THRESHOLD_BREACH" if breached else "OK",
        remediation_hint="Portfolio cash is outside policy bands." if breached else None,
    )


def _single_position_failure(pos, limit_w: Decimal) -> RuleResult:
    return _result(
        rule_id="SINGLE_POSITION_MAX",
        severity="HARD",
        status="FAIL",
        measured=pos.weight,
        threshold={"max": limit_w},
        reason_code="LIMIT_BREACH",
        remediation_hint=f"Instrument {pos.key} exceeds max weight.",
    )


def _single_position_no_limit_result() -> RuleResult:
    return _result(
        rule_id="SINGLE_POSITION_MAX",
        severity="HARD",
        status="PASS",
        measured=_ZERO,
        threshold={"max": Decimal("-1")},
        reason_code="NO_LIMIT_SET",
    )


def _single_position_failures(
    state: SimulatedState,
    limit_w: Decimal,
) -> list[RuleResult]:
    return [
        _single_position_failure(pos, limit_w)
        for pos in state.allocation_by_instrument
        if pos.weight > limit_w + _SINGLE_POSITION_TOLERANCE
    ]


def _single_position_pass_result(state: SimulatedState, limit_w: Decimal) -> RuleResult:
    max_measured = max((pos.weight for pos in state.allocation_by_instrument), default=_ZERO)
    return _result(
        rule_id="SINGLE_POSITION_MAX",
        severity="HARD",
        status="PASS",
        measured=max_measured,
        threshold={"max": limit_w},
        reason_code="OK",
    )


def _single_position_results(state: SimulatedState, options: EngineOptions) -> list[RuleResult]:
    limit_w = options.single_position_max_weight
    if limit_w is None:
        return [_single_position_no_limit_result()]

    failures = _single_position_failures(state, limit_w)
    if failures:
        return failures

    return [_single_position_pass_result(state, limit_w)]


def _data_quality_issue_count(options: EngineOptions, diagnostics: DiagnosticsData) -> int:
    dq_count = len(diagnostics.data_quality.get("shelf_missing", []))
    if options.block_on_missing_prices:
        dq_count += len(diagnostics.data_quality.get("price_missing", []))
    if options.block_on_missing_fx:
        dq_count += len(diagnostics.data_quality.get("fx_missing", []))
    return dq_count


def _data_quality_result(options: EngineOptions, diagnostics: DiagnosticsData) -> RuleResult:
    dq_count = _data_quality_issue_count(options, diagnostics)
    breached = dq_count > 0
    return _result(
        rule_id="DATA_QUALITY",
        severity="HARD",
        status="FAIL" if breached else "PASS",
        measured=Decimal(dq_count),
        threshold={"max": _ZERO},
        reason_code="MISSING_DATA" if breached else "OK",
        remediation_hint="Check diagnostics for missing prices/FX." if breached else None,
    )


def _min_trade_size_result(diagnostics: DiagnosticsData) -> RuleResult:
    suppressed_count = len(diagnostics.suppressed_intents)
    return _result(
        rule_id="MIN_TRADE_SIZE",
        severity="SOFT",
        status="PASS",
        measured=Decimal(suppressed_count),
        threshold={"min": _ZERO},
        reason_code="INTENTS_SUPPRESSED" if suppressed_count > 0 else "OK",
    )


def _negative_position_quantity(state: SimulatedState) -> Decimal | None:
    negative_quantities = [p.quantity for p in state.positions if p.quantity < _ZERO]
    return min(negative_quantities) if negative_quantities else None


def _no_shorting_result(state: SimulatedState) -> RuleResult:
    min_qty = _negative_position_quantity(state)
    breached = min_qty is not None
    return _result(
        rule_id="NO_SHORTING",
        severity="HARD",
        status="FAIL" if breached else "PASS",
        measured=min_qty if min_qty is not None else _ZERO,
        threshold={"min": _ZERO},
        reason_code="SELL_EXCEEDS_HOLDINGS" if breached else "OK",
        remediation_hint="Reduce sell quantity." if breached else None,
    )


def _negative_cash_amount(state: SimulatedState) -> Decimal | None:
    negative_amounts = [c.amount for c in state.cash_balances if c.amount < _ZERO]
    return min(negative_amounts) if negative_amounts else None


def _insufficient_cash_result(state: SimulatedState) -> RuleResult:
    min_cash = _negative_cash_amount(state)
    breached = min_cash is not None
    return _result(
        rule_id="INSUFFICIENT_CASH",
        severity="HARD",
        status="FAIL" if breached else "PASS",
        measured=min_cash if min_cash is not None else _ZERO,
        threshold={"min": _ZERO},
        reason_code="CASH_BALANCE_NEGATIVE" if breached else "OK",
        remediation_hint="Ensure sufficient funding." if breached else None,
    )


class RuleEngine:
    """
    Evaluates business rules against the simulated after-state.
    Supports HARD (Block), SOFT (Review), and INFO (Log) severities.
    Enforces RFC-0006B: All core rules must emit a result.
    """

    @staticmethod
    def evaluate(
        state: SimulatedState, options: EngineOptions, diagnostics: DiagnosticsData
    ) -> List[RuleResult]:
        return [
            _cash_band_result(state, options),
            *_single_position_results(state, options),
            _data_quality_result(options, diagnostics),
            _min_trade_size_result(diagnostics),
            _no_shorting_result(state),
            _insufficient_cash_result(state),
        ]
