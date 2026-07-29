"""Durable, deterministic receipts for published position valuations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from ..calculation_lineage import (
    CalculationLineage,
    FinancialSourceReference,
    canonical_content_hash,
    require_sha256_digest,
)
from .source_facts import MarketPriceQuoteBasis, MarketPriceSourceFact


class ValuationReceiptSupportability(StrEnum):
    """Bounded posture for a persisted valuation receipt."""

    SUPPORTED = "SUPPORTED"
    LEGACY_UNSCOPED = "LEGACY_UNSCOPED"


@dataclass(frozen=True, slots=True)
class ValuationSnapshotIdentity:
    """Stable identity of the snapshot whose calculation a receipt proves."""

    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int

    def __post_init__(self) -> None:
        for field_name in ("portfolio_id", "security_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        if type(self.valuation_date) is not date:
            raise TypeError("valuation_date must be an exact date")
        if not isinstance(self.epoch, int) or isinstance(self.epoch, bool):
            raise TypeError("epoch must be an integer")
        if self.epoch < 0:
            raise ValueError("epoch must be non-negative")

    def lineage_payload(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "portfolio_id": self.portfolio_id,
            "security_id": self.security_id,
            "valuation_date": self.valuation_date,
        }


@dataclass(frozen=True, slots=True)
class ValuationCalculationReceipt:
    """Complete authoritative receipt or explicit legacy compatibility evidence."""

    snapshot_identity: ValuationSnapshotIdentity
    supportability: ValuationReceiptSupportability
    supportability_reasons: tuple[str, ...]
    policy_id: str | None
    policy_version: int | None
    assignment_version: int | None
    assignment_content_hash: str | None
    policy_assignment_source: FinancialSourceReference | None
    quote_basis: MarketPriceQuoteBasis | None
    price_fact_version: int | None
    price_fact_content_hash: str | None
    market_price_source: FinancialSourceReference | None
    calculation_lineage: CalculationLineage | None
    receipt_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_identity, ValuationSnapshotIdentity):
            raise TypeError("snapshot_identity must be a ValuationSnapshotIdentity")
        if not isinstance(self.supportability, ValuationReceiptSupportability):
            raise TypeError("supportability must be a ValuationReceiptSupportability")
        normalized_reasons = tuple(
            sorted(
                {
                    reason.strip()
                    for reason in self.supportability_reasons
                    if isinstance(reason, str) and reason.strip()
                }
            )
        )
        if len(normalized_reasons) != len(self.supportability_reasons):
            raise ValueError("supportability_reasons must be unique nonblank strings")
        object.__setattr__(self, "supportability_reasons", normalized_reasons)
        if not normalized_reasons:
            raise ValueError("supportability_reasons must not be empty")
        if self.supportability is ValuationReceiptSupportability.SUPPORTED:
            self._validate_authoritative_fields()
        else:
            self._validate_legacy_fields()
        require_sha256_digest(self.receipt_hash, "receipt_hash")
        expected_hash = canonical_content_hash(self.content_payload())
        if self.receipt_hash != expected_hash:
            raise ValueError("receipt_hash does not match receipt content")

    def _validate_authoritative_fields(self) -> None:
        required = {
            "assignment_content_hash": self.assignment_content_hash,
            "assignment_version": self.assignment_version,
            "calculation_lineage": self.calculation_lineage,
            "market_price_source": self.market_price_source,
            "policy_assignment_source": self.policy_assignment_source,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "price_fact_content_hash": self.price_fact_content_hash,
            "price_fact_version": self.price_fact_version,
            "quote_basis": self.quote_basis,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"supported valuation receipt is missing fields: {sorted(missing)}")
        assert self.policy_id is not None
        if not self.policy_id.strip():
            raise ValueError("policy_id must be nonblank")
        assert self.policy_version is not None
        assert self.assignment_version is not None
        assert self.price_fact_version is not None
        if min(self.policy_version, self.assignment_version, self.price_fact_version) < 1:
            raise ValueError("policy and source versions must be positive")
        assert self.assignment_content_hash is not None
        assert self.price_fact_content_hash is not None
        require_sha256_digest(
            self.assignment_content_hash,
            "assignment_content_hash",
        )
        require_sha256_digest(
            self.price_fact_content_hash,
            "price_fact_content_hash",
        )

    def _validate_legacy_fields(self) -> None:
        authoritative_values = (
            self.policy_id,
            self.policy_version,
            self.assignment_version,
            self.assignment_content_hash,
            self.policy_assignment_source,
            self.quote_basis,
            self.price_fact_version,
            self.price_fact_content_hash,
            self.market_price_source,
            self.calculation_lineage,
        )
        if any(value is not None for value in authoritative_values):
            raise ValueError("legacy valuation receipt cannot claim authoritative evidence")

    def content_payload(self) -> dict[str, object]:
        """Return canonical receipt content excluding its self-authenticating hash."""

        return _content_payload(
            snapshot_identity=self.snapshot_identity,
            supportability=self.supportability,
            supportability_reasons=self.supportability_reasons,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            assignment_version=self.assignment_version,
            assignment_content_hash=self.assignment_content_hash,
            policy_assignment_source=self.policy_assignment_source,
            quote_basis=self.quote_basis,
            price_fact_version=self.price_fact_version,
            price_fact_content_hash=self.price_fact_content_hash,
            market_price_source=self.market_price_source,
            calculation_lineage=self.calculation_lineage,
        )


def build_authoritative_valuation_receipt(
    *,
    snapshot_identity: ValuationSnapshotIdentity,
    policy_id: str,
    policy_version: int,
    assignment_version: int,
    assignment_content_hash: str,
    policy_assignment_source: FinancialSourceReference,
    price_fact: MarketPriceSourceFact,
    calculation_lineage: CalculationLineage,
) -> ValuationCalculationReceipt:
    """Build a supported receipt from the exact authorities used by calculation."""

    supportability = ValuationReceiptSupportability.SUPPORTED
    supportability_reasons = ("EXACT_POLICY_AND_PRICE_AUTHORITY",)
    normalized_policy_id = policy_id.strip()
    price_fact_content_hash = price_fact.content_hash()
    receipt_hash = canonical_content_hash(
        _content_payload(
            snapshot_identity=snapshot_identity,
            supportability=supportability,
            supportability_reasons=supportability_reasons,
            policy_id=normalized_policy_id,
            policy_version=policy_version,
            assignment_version=assignment_version,
            assignment_content_hash=assignment_content_hash,
            policy_assignment_source=policy_assignment_source,
            quote_basis=price_fact.quote_basis,
            price_fact_version=price_fact.fact_version,
            price_fact_content_hash=price_fact_content_hash,
            market_price_source=price_fact.source_reference,
            calculation_lineage=calculation_lineage,
        )
    )
    return ValuationCalculationReceipt(
        snapshot_identity=snapshot_identity,
        supportability=supportability,
        supportability_reasons=supportability_reasons,
        policy_id=normalized_policy_id,
        policy_version=policy_version,
        assignment_version=assignment_version,
        assignment_content_hash=assignment_content_hash,
        policy_assignment_source=policy_assignment_source,
        quote_basis=price_fact.quote_basis,
        price_fact_version=price_fact.fact_version,
        price_fact_content_hash=price_fact_content_hash,
        market_price_source=price_fact.source_reference,
        calculation_lineage=calculation_lineage,
        receipt_hash=receipt_hash,
    )


def build_legacy_valuation_receipt(
    *,
    snapshot_identity: ValuationSnapshotIdentity,
) -> ValuationCalculationReceipt:
    """Build explicit evidence for the bounded unscoped compatibility route."""

    supportability = ValuationReceiptSupportability.LEGACY_UNSCOPED
    supportability_reasons = ("PORTFOLIO_VALUATION_SCOPE_UNASSIGNED",)
    receipt_hash = canonical_content_hash(
        _content_payload(
            snapshot_identity=snapshot_identity,
            supportability=supportability,
            supportability_reasons=supportability_reasons,
            policy_id=None,
            policy_version=None,
            assignment_version=None,
            assignment_content_hash=None,
            policy_assignment_source=None,
            quote_basis=None,
            price_fact_version=None,
            price_fact_content_hash=None,
            market_price_source=None,
            calculation_lineage=None,
        )
    )
    return ValuationCalculationReceipt(
        snapshot_identity=snapshot_identity,
        supportability=supportability,
        supportability_reasons=supportability_reasons,
        policy_id=None,
        policy_version=None,
        assignment_version=None,
        assignment_content_hash=None,
        policy_assignment_source=None,
        quote_basis=None,
        price_fact_version=None,
        price_fact_content_hash=None,
        market_price_source=None,
        calculation_lineage=None,
        receipt_hash=receipt_hash,
    )


def _content_payload(
    *,
    snapshot_identity: ValuationSnapshotIdentity,
    supportability: ValuationReceiptSupportability,
    supportability_reasons: tuple[str, ...],
    policy_id: str | None,
    policy_version: int | None,
    assignment_version: int | None,
    assignment_content_hash: str | None,
    policy_assignment_source: FinancialSourceReference | None,
    quote_basis: MarketPriceQuoteBasis | None,
    price_fact_version: int | None,
    price_fact_content_hash: str | None,
    market_price_source: FinancialSourceReference | None,
    calculation_lineage: CalculationLineage | None,
) -> dict[str, object]:
    return {
        "assignment_content_hash": assignment_content_hash,
        "assignment_version": assignment_version,
        "calculation_lineage": (
            calculation_lineage.lineage_payload() if calculation_lineage is not None else None
        ),
        "market_price_source": (
            market_price_source.lineage_payload() if market_price_source is not None else None
        ),
        "policy_assignment_source": (
            policy_assignment_source.lineage_payload()
            if policy_assignment_source is not None
            else None
        ),
        "policy_id": policy_id,
        "policy_version": policy_version,
        "price_fact_content_hash": price_fact_content_hash,
        "price_fact_version": price_fact_version,
        "quote_basis": quote_basis,
        "snapshot_identity": snapshot_identity.lineage_payload(),
        "supportability": supportability,
        "supportability_reasons": supportability_reasons,
    }
