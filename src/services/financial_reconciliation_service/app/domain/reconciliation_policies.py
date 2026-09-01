from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

from portfolio_common.domain.decimal_amount import required_decimal
from portfolio_common.domain.financial.precision import DecimalPrecisionPolicy
from portfolio_common.domain.market_data.market_price import (
    coerce_positive_market_price_or_none,
)
from portfolio_common.domain.valuation import (
    BOND_QUOTE_AUTHORITY_REQUIRED_REASON,
    PositionScaling,
    PositionValuationEconomicInputs,
    PrincipalBasis,
    UnknownValuationPolicyError,
    UnsupportedValuationError,
    ValuationInputBasis,
    ValuationOutputMeasure,
    calculate_position_valuation_local_economics,
    requires_bond_quote_authority,
    resolve_position_valuation_policy,
)

DEFAULT_VALUE_TOLERANCE = Decimal("0.0001")
RECONCILIATION_TOLERANCE_PRECISION_V1 = DecimalPrecisionPolicy(
    name="reconciliation-tolerance-v1",
    precision=18,
    scale=10,
)

DEFAULT_RECONCILIATION_FINDING_OWNER = "FINANCIAL_CONTROL_OPERATIONS"
_FINDING_OWNER_BY_RECONCILIATION_TYPE = {
    "position_valuation": "VALUATION_OPERATIONS",
    "timeseries_integrity": "PORTFOLIO_CONTROL_OPERATIONS",
    "transaction_cashflow": "TRANSACTION_OPERATIONS",
}
_REPAIR_RECOMMENDATION_BY_FINDING_TYPE = {
    "cashflow_rule_mismatch": "REBUILD_CASHFLOW_FROM_GOVERNED_RULE",
    "fx_rate_not_on_valuation_date": "REVALUE_POSITION_WITH_EXACT_DATE_FX",
    "invalid_market_price": "CORRECT_MARKET_PRICE_SOURCE",
    "market_value_local_mismatch": "REVALUE_POSITION",
    "missing_bond_quote_authority": "ASSIGN_VALUATION_QUOTE_POLICY",
    "missing_cashflow": "REGENERATE_CASHFLOW",
    "missing_portfolio_timeseries": "REBUILD_DERIVED_TIMESERIES",
    "missing_position_timeseries": "REBUILD_DERIVED_TIMESERIES",
    "portfolio_timeseries_aggregate_mismatch": "REBUILD_PORTFOLIO_TIMESERIES",
    "position_timeseries_completeness_gap": "REBUILD_DERIVED_TIMESERIES",
    "unrealized_gain_loss_local_mismatch": "REVALUE_POSITION",
    "unsupported_authoritative_valuation_receipt": ("REBUILD_VALUATION_WITH_SUPPORTED_POLICY"),
}
DEFAULT_REPAIR_RECOMMENDATION = "REVIEW_RECONCILIATION_BREAK"


def resolve_value_tolerance(override: Decimal | None) -> Decimal:
    """Preserve an explicit zero override and default only an omitted control."""

    if override is None:
        return DEFAULT_VALUE_TOLERANCE
    return cast(
        Decimal,
        RECONCILIATION_TOLERANCE_PRECISION_V1.require_exact(
            override,
            field_name="tolerance",
        ),
    )


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
    tolerance: Decimal | None = None
    observed_delta: Decimal | None = None


def reconciliation_finding_owner(reconciliation_type: str) -> str:
    return _FINDING_OWNER_BY_RECONCILIATION_TYPE.get(
        reconciliation_type.strip().lower(),
        DEFAULT_RECONCILIATION_FINDING_OWNER,
    )


def reconciliation_repair_recommendation(finding_type: str) -> str:
    return _REPAIR_RECOMMENDATION_BY_FINDING_TYPE.get(
        finding_type.strip().lower(),
        DEFAULT_REPAIR_RECOMMENDATION,
    )


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
    cost_basis_reporting: object
    cost_basis_local: object
    unrealized_gain_loss_local: object
    product_type: str | None
    valuation_fx_rate_date: date | None = None
    valuation_receipt: PositionValuationReceiptEvidence | None = None


@dataclass(frozen=True, slots=True)
class PositionValuationReceiptEvidence:
    """Minimum persisted authority evidence required for independent reconciliation."""

    supportability: str
    policy_id: str | None
    policy_version: int | None
    quote_basis: str | None
    receipt_hash: str


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


def _authoritative_market_value_local(
    *,
    quantity: Decimal,
    market_price: Decimal,
    receipt: PositionValuationReceiptEvidence,
) -> Decimal | None:
    if (
        not isinstance(receipt.policy_id, str)
        or not isinstance(receipt.policy_version, int)
        or isinstance(receipt.policy_version, bool)
        or not isinstance(receipt.quote_basis, str)
    ):
        return None
    try:
        policy = resolve_position_valuation_policy(
            receipt.policy_id,
            receipt.policy_version,
        )
    except (TypeError, ValueError, UnknownValuationPolicyError):
        return None
    if (
        policy.input_basis.value != receipt.quote_basis
        or policy.position_scaling is not PositionScaling.QUANTITY
        or policy.principal_basis is not PrincipalBasis.POSITION_UNITS
        or policy.input_basis is not ValuationInputBasis.UNIT_PRICE
    ):
        return None
    if policy.output_measure is not ValuationOutputMeasure.MARKET_VALUE:
        return None
    try:
        economics = calculate_position_valuation_local_economics(
            policy=policy,
            inputs=PositionValuationEconomicInputs(
                source_value=market_price,
                signed_quantity=quantity,
            ),
        )
    except UnsupportedValuationError:
        return None
    return cast(Decimal | None, economics.total_market_value_local)


def _unsupported_authoritative_receipt_finding(
    evidence: PositionValuationEvidence,
    receipt: PositionValuationReceiptEvidence,
) -> ReconciliationFinding:
    return ReconciliationFinding(
        reconciliation_type="position_valuation",
        finding_type="unsupported_authoritative_valuation_receipt",
        severity="ERROR",
        portfolio_id=evidence.portfolio_id,
        security_id=evidence.security_id,
        transaction_id=None,
        business_date=evidence.business_date,
        epoch=evidence.epoch,
        expected_value={"supportability": "SUPPORTED_UNIT_PRICE_QUANTITY"},
        observed_value={
            "policy_id": receipt.policy_id,
            "policy_version": receipt.policy_version,
            "quote_basis": receipt.quote_basis,
            "supportability": receipt.supportability,
        },
        detail={"receipt_hash": receipt.receipt_hash},
    )


def _missing_bond_quote_authority_finding(
    evidence: PositionValuationEvidence,
) -> ReconciliationFinding:
    return ReconciliationFinding(
        reconciliation_type="position_valuation",
        finding_type="missing_bond_quote_authority",
        severity="ERROR",
        portfolio_id=evidence.portfolio_id,
        security_id=evidence.security_id,
        transaction_id=None,
        business_date=evidence.business_date,
        epoch=evidence.epoch,
        expected_value={"valuation_receipt_supportability": "SUPPORTED"},
        observed_value={
            "valuation_receipt_supportability": (
                evidence.valuation_receipt.supportability
                if evidence.valuation_receipt is not None
                else None
            )
        },
        detail={"reason": BOND_QUOTE_AUTHORITY_REQUIRED_REASON},
    )


def requires_authoritative_fx_rate(from_currency: str, to_currency: str) -> bool:
    return bool(from_currency and to_currency and from_currency != to_currency)


def _fx_rate_date_finding(
    evidence: PositionValuationEvidence,
) -> ReconciliationFinding | None:
    fx_rate_date = evidence.valuation_fx_rate_date
    if fx_rate_date is None or fx_rate_date == evidence.business_date:
        return None
    return ReconciliationFinding(
        reconciliation_type="position_valuation",
        finding_type="fx_rate_not_on_valuation_date",
        severity="ERROR",
        portfolio_id=evidence.portfolio_id,
        security_id=evidence.security_id,
        transaction_id=None,
        business_date=evidence.business_date,
        epoch=evidence.epoch,
        expected_value={"valuation_fx_rate_date": evidence.business_date.isoformat()},
        observed_value={"valuation_fx_rate_date": fx_rate_date.isoformat()},
        detail={"reason": "recorded FX authority is not owned by the valuation date"},
    )


def position_valuation_reconciliation_findings(
    *,
    evidence: PositionValuationEvidence,
    tolerance: Decimal,
) -> list[ReconciliationFinding]:
    findings: list[ReconciliationFinding] = []
    if fx_rate_date_finding := _fx_rate_date_finding(evidence):
        findings.append(fx_rate_date_finding)
    quantity = required_decimal(evidence.quantity, field_name="snapshot.quantity")
    cost_basis_local = required_decimal(
        evidence.cost_basis_local,
        field_name="snapshot.cost_basis_local",
    )
    cost_basis_reporting = required_decimal(
        evidence.cost_basis_reporting,
        field_name="snapshot.cost_basis_reporting",
    )
    market_price = coerce_positive_market_price_or_none(evidence.market_price)
    if market_price is None:
        return findings + [
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

    receipt = evidence.valuation_receipt
    if receipt is None or receipt.supportability == "LEGACY_UNSCOPED":
        if requires_bond_quote_authority(
            product_type=evidence.product_type,
            quantity=quantity,
            cost_basis_reporting=cost_basis_reporting,
            cost_basis_local=cost_basis_local,
        ):
            return findings + [_missing_bond_quote_authority_finding(evidence)]
        expected_market_value = quantity * market_price
    elif receipt.supportability == "SUPPORTED":
        authoritative_market_value = _authoritative_market_value_local(
            quantity=quantity,
            market_price=market_price,
            receipt=receipt,
        )
        if authoritative_market_value is None:
            return findings + [_unsupported_authoritative_receipt_finding(evidence, receipt)]
        expected_market_value = authoritative_market_value
    else:
        return findings + [_unsupported_authoritative_receipt_finding(evidence, receipt)]
    expected_unrealized = expected_market_value - cost_basis_local
    observed_market_value = required_decimal(
        evidence.market_value_local,
        field_name="snapshot.market_value_local",
    )
    observed_unrealized = required_decimal(
        evidence.unrealized_gain_loss_local,
        field_name="snapshot.unrealized_gain_loss_local",
    )

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
                tolerance=tolerance,
                observed_delta=market_delta,
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
                tolerance=tolerance,
                observed_delta=unrealized_delta,
            )
        )
    return findings
