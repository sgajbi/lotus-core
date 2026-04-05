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
        results = []

        cash_weight = next(
            (a.weight for a in state.allocation_by_asset_class if a.key == "CASH"), Decimal("0")
        )
        min_w = options.cash_band_min_weight
        max_w = options.cash_band_max_weight

        if cash_weight < min_w or cash_weight > max_w:
            results.append(
                RuleResult(
                    rule_id="CASH_BAND",
                    severity="SOFT",
                    status="FAIL",
                    measured=cash_weight,
                    threshold={"min": min_w, "max": max_w},
                    reason_code="THRESHOLD_BREACH",
                    remediation_hint="Portfolio cash is outside policy bands.",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id="CASH_BAND",
                    severity="SOFT",
                    status="PASS",
                    measured=cash_weight,
                    threshold={"min": min_w, "max": max_w},
                    reason_code="OK",
                )
            )

        limit_w = options.single_position_max_weight
        if limit_w is not None:
            breach = False
            max_measured = Decimal("0")
            for pos in state.allocation_by_instrument:
                max_measured = max(max_measured, pos.weight)
                if pos.weight > limit_w + Decimal("0.001"):
                    breach = True
                    results.append(
                        RuleResult(
                            rule_id="SINGLE_POSITION_MAX",
                            severity="HARD",
                            status="FAIL",
                            measured=pos.weight,
                            threshold={"max": limit_w},
                            reason_code="LIMIT_BREACH",
                            remediation_hint=f"Instrument {pos.key} exceeds max weight.",
                        )
                    )

            if not breach:
                results.append(
                    RuleResult(
                        rule_id="SINGLE_POSITION_MAX",
                        severity="HARD",
                        status="PASS",
                        measured=max_measured,
                        threshold={"max": limit_w},
                        reason_code="OK",
                    )
                )
        else:
            results.append(
                RuleResult(
                    rule_id="SINGLE_POSITION_MAX",
                    severity="HARD",
                    status="PASS",
                    measured=Decimal("0"),
                    threshold={"max": Decimal("-1")},
                    reason_code="NO_LIMIT_SET",
                )
            )

        dq_count = 0

        if options.block_on_missing_prices:
            dq_count += len(diagnostics.data_quality.get("price_missing", []))

        if options.block_on_missing_fx:
            dq_count += len(diagnostics.data_quality.get("fx_missing", []))

        dq_count += len(diagnostics.data_quality.get("shelf_missing", []))

        if dq_count > 0:
            results.append(
                RuleResult(
                    rule_id="DATA_QUALITY",
                    severity="HARD",
                    status="FAIL",
                    measured=Decimal(dq_count),
                    threshold={"max": Decimal("0")},
                    reason_code="MISSING_DATA",
                    remediation_hint="Check diagnostics for missing prices/FX.",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id="DATA_QUALITY",
                    severity="HARD",
                    status="PASS",
                    measured=Decimal(dq_count),
                    threshold={"max": Decimal("0")},
                    reason_code="OK",
                )
            )

        suppressed_count = len(diagnostics.suppressed_intents)
        if suppressed_count > 0:
            results.append(
                RuleResult(
                    rule_id="MIN_TRADE_SIZE",
                    severity="SOFT",
                    status="PASS",
                    measured=Decimal(suppressed_count),
                    threshold={"min": Decimal("0")},
                    reason_code="INTENTS_SUPPRESSED",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id="MIN_TRADE_SIZE",
                    severity="SOFT",
                    status="PASS",
                    measured=Decimal("0"),
                    threshold={"min": Decimal("0")},
                    reason_code="OK",
                )
            )

        shorting_breach = False
        min_qty = Decimal("0")
        for p in state.positions:
            if p.quantity < Decimal("0"):
                shorting_breach = True
                min_qty = min(min_qty, p.quantity)

        if shorting_breach:
            results.append(
                RuleResult(
                    rule_id="NO_SHORTING",
                    severity="HARD",
                    status="FAIL",
                    measured=min_qty,
                    threshold={"min": Decimal("0")},
                    reason_code="SELL_EXCEEDS_HOLDINGS",
                    remediation_hint="Reduce sell quantity.",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id="NO_SHORTING",
                    severity="HARD",
                    status="PASS",
                    measured=Decimal("0"),
                    threshold={"min": Decimal("0")},
                    reason_code="OK",
                )
            )

        cash_breach = False
        min_cash = Decimal("0")
        for c in state.cash_balances:
            if c.amount < Decimal("0"):
                cash_breach = True
                min_cash = min(min_cash, c.amount)

        if cash_breach:
            results.append(
                RuleResult(
                    rule_id="INSUFFICIENT_CASH",
                    severity="HARD",
                    status="FAIL",
                    measured=min_cash,
                    threshold={"min": Decimal("0")},
                    reason_code="CASH_BALANCE_NEGATIVE",
                    remediation_hint="Ensure sufficient funding.",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id="INSUFFICIENT_CASH",
                    severity="HARD",
                    status="PASS",
                    measured=Decimal("0"),
                    threshold={"min": Decimal("0")},
                    reason_code="OK",
                )
            )

        return results
