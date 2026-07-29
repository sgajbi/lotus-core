"""Map persisted valuation inputs into immutable domain source evidence."""

from __future__ import annotations

from datetime import datetime

from portfolio_common.database_models import FxRate, Portfolio, PositionHistory
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceSourceFact,
    PositionValuationEvidence,
    ResolvedValuationPolicyAssignment,
    canonical_content_hash,
)


def build_authoritative_valuation_evidence(
    *,
    assignment: ResolvedValuationPolicyAssignment,
    price_fact: MarketPriceSourceFact,
    position: PositionHistory,
    portfolio: Portfolio,
    fx_rate: FxRate | None,
) -> PositionValuationEvidence:
    """Build the evidence consumed by the currently supported runtime inputs."""

    position_reference = _position_history_reference(position)
    portfolio_reference = _portfolio_reference(portfolio)
    fx_reference = _fx_rate_reference(fx_rate) if fx_rate is not None else None
    return PositionValuationEvidence(
        policy_assignment=assignment.assignment.source_reference(),
        source_value=price_fact.source_reference,
        source_currency=price_fact.source_reference,
        reporting_currency=portfolio_reference,
        signed_quantity=position_reference,
        direct_source_to_reporting_fx_rate=fx_reference,
    )


def _position_history_reference(position: PositionHistory) -> FinancialSourceReference:
    observed_at = _aware_observed_at(position.updated_at, "position.updated_at")
    return FinancialSourceReference(
        source_system="lotus-core.position-history",
        source_record_id=(
            f"{_required_text(position.portfolio_id, 'position.portfolio_id')}:"
            f"{_required_text(position.security_id, 'position.security_id')}:"
            f"{position.epoch}:{position.position_date.isoformat()}:"
            f"{_required_text(position.transaction_id, 'position.transaction_id')}"
        ),
        source_revision=_row_revision(position.id, observed_at),
        source_content_hash=canonical_content_hash(
            {
                "cost_basis": position.cost_basis,
                "cost_basis_local": position.cost_basis_local,
                "epoch": position.epoch,
                "position_date": position.position_date,
                "quantity": position.quantity,
                "transaction_id": position.transaction_id,
            }
        ),
        observed_at=observed_at,
    )


def _portfolio_reference(portfolio: Portfolio) -> FinancialSourceReference:
    observed_at = _aware_observed_at(portfolio.updated_at, "portfolio.updated_at")
    return FinancialSourceReference(
        source_system="lotus-core.portfolio",
        source_record_id=_required_text(portfolio.portfolio_id, "portfolio.portfolio_id"),
        source_revision=_row_revision(portfolio.id, observed_at),
        source_content_hash=canonical_content_hash(
            {
                "base_currency": portfolio.base_currency,
                "legal_book_id": portfolio.legal_book_id,
                "portfolio_id": portfolio.portfolio_id,
                "tenant_id": portfolio.tenant_id,
            }
        ),
        observed_at=observed_at,
    )


def _fx_rate_reference(fx_rate: FxRate) -> FinancialSourceReference:
    observed_at = _aware_observed_at(fx_rate.updated_at, "fx_rate.updated_at")
    return FinancialSourceReference(
        source_system="lotus-core.fx-rate",
        source_record_id=(
            f"{_required_text(fx_rate.from_currency, 'fx_rate.from_currency')}:"
            f"{_required_text(fx_rate.to_currency, 'fx_rate.to_currency')}:"
            f"{fx_rate.rate_date.isoformat()}"
        ),
        source_revision=_row_revision(fx_rate.id, observed_at),
        source_content_hash=canonical_content_hash(
            {
                "from_currency": fx_rate.from_currency,
                "rate": fx_rate.rate,
                "rate_date": fx_rate.rate_date,
                "to_currency": fx_rate.to_currency,
            }
        ),
        observed_at=observed_at,
    )


def _row_revision(row_id: object, observed_at: datetime) -> str:
    if not isinstance(row_id, int) or isinstance(row_id, bool) or row_id < 1:
        raise ValueError("authoritative evidence requires a positive persisted row id")
    return f"row-{row_id}@{observed_at.isoformat()}"


def _aware_observed_at(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    return normalized
