from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.decimal_amounts import required_decimal
from portfolio_common.market_prices import coerce_positive_market_price_or_none
from portfolio_common.valuation_prices import resolve_valuation_unit_price

DEFAULT_VALUE_TOLERANCE = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    reconciliation_type: str
    finding_type: str
    severity: str
    portfolio_id: str | None
    security_id: str | None
    transaction_id: str | None
    business_date: date | None
    epoch: int | None
    expected_value: dict[str, Any] | None
    observed_value: dict[str, Any] | None
    detail: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    examined_count: int
    finding_count: int
    error_count: int
    warning_count: int
    passed: bool

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "examined_count": self.examined_count,
            "finding_count": self.finding_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class PositionValuationEvidence:
    portfolio_id: str
    security_id: str
    business_date: date
    epoch: int
    quantity: object
    market_price: object
    market_value_local: object
    cost_basis_local: object
    unrealized_gain_loss_local: object
    product_type: str | None


def build_reconciliation_summary(
    *,
    examined: int,
    findings: Sequence[ReconciliationFinding],
) -> ReconciliationSummary:
    error_count = sum(1 for finding in findings if finding.severity == "ERROR")
    warning_count = sum(1 for finding in findings if finding.severity == "WARNING")
    return ReconciliationSummary(
        examined_count=examined,
        finding_count=len(findings),
        error_count=error_count,
        warning_count=warning_count,
        passed=error_count == 0,
    )


def expected_market_value_local(
    *,
    quantity: Decimal,
    market_price: Decimal,
    cost_basis_local: Decimal,
    product_type: str | None,
) -> Decimal:
    valuation_price_local = resolve_valuation_unit_price(
        market_price=market_price,
        quantity=quantity,
        cost_basis_local=cost_basis_local,
        product_type=product_type,
    )
    return quantity * valuation_price_local


def requires_authoritative_fx_rate(from_currency: str, to_currency: str) -> bool:
    return bool(from_currency and to_currency and from_currency != to_currency)


def position_valuation_reconciliation_findings(
    *,
    evidence: PositionValuationEvidence,
    tolerance: Decimal,
) -> list[ReconciliationFinding]:
    quantity = required_decimal(evidence.quantity, field_name="snapshot.quantity")
    cost_basis_local = required_decimal(
        evidence.cost_basis_local,
        field_name="snapshot.cost_basis_local",
    )
    market_price = coerce_positive_market_price_or_none(evidence.market_price)
    if market_price is None:
        return [
            ReconciliationFinding(
                reconciliation_type="position_valuation",
                finding_type="invalid_market_price",
                severity="ERROR",
                portfolio_id=evidence.portfolio_id,
                security_id=evidence.security_id,
                transaction_id=None,
                business_date=evidence.business_date,
                epoch=evidence.epoch,
                expected_value={"market_price": ">0"},
                observed_value={"market_price": str(evidence.market_price)},
                detail={
                    "quantity": str(evidence.quantity),
                    "product_type": evidence.product_type,
                },
            )
        ]

    expected_market_value = expected_market_value_local(
        quantity=quantity,
        market_price=market_price,
        cost_basis_local=cost_basis_local,
        product_type=evidence.product_type,
    )
    expected_unrealized = expected_market_value - cost_basis_local
    observed_market_value = required_decimal(
        evidence.market_value_local,
        field_name="snapshot.market_value_local",
    )
    observed_unrealized = required_decimal(
        evidence.unrealized_gain_loss_local,
        field_name="snapshot.unrealized_gain_loss_local",
    )

    findings: list[ReconciliationFinding] = []
    market_delta = observed_market_value - expected_market_value
    if abs(market_delta) > tolerance:
        findings.append(
            ReconciliationFinding(
                reconciliation_type="position_valuation",
                finding_type="market_value_local_mismatch",
                severity="ERROR",
                portfolio_id=evidence.portfolio_id,
                security_id=evidence.security_id,
                transaction_id=None,
                business_date=evidence.business_date,
                epoch=evidence.epoch,
                expected_value={"market_value_local": str(expected_market_value)},
                observed_value={
                    "market_value_local": str(observed_market_value),
                    "delta": str(market_delta),
                },
                detail={
                    "quantity": str(evidence.quantity),
                    "market_price": str(evidence.market_price),
                    "product_type": evidence.product_type,
                },
            )
        )

    unrealized_delta = observed_unrealized - expected_unrealized
    if abs(unrealized_delta) > tolerance:
        findings.append(
            ReconciliationFinding(
                reconciliation_type="position_valuation",
                finding_type="unrealized_gain_loss_local_mismatch",
                severity="ERROR",
                portfolio_id=evidence.portfolio_id,
                security_id=evidence.security_id,
                transaction_id=None,
                business_date=evidence.business_date,
                epoch=evidence.epoch,
                expected_value={"unrealized_gain_loss_local": str(expected_unrealized)},
                observed_value={
                    "unrealized_gain_loss_local": str(observed_unrealized),
                    "delta": str(unrealized_delta),
                },
                detail={
                    "market_value_local": str(observed_market_value),
                    "cost_basis_local": str(evidence.cost_basis_local),
                    "product_type": evidence.product_type,
                },
            )
        )
    return findings
