"""Deterministic identity helpers for RFC-0083 portfolio reconstruction scopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import TypeAlias

SNAPSHOT_ID_PREFIX = "pss"
RECONSTRUCTION_SCOPE_ID_PREFIX = "rs"
RECONSTRUCTION_SCOPE_VERSION = "v1"
CURRENT_RESTATEMENT_VERSION = "current"

ReconstructionScopeValue: TypeAlias = str | int | bool | date | datetime | None
ReconstructionScopeEntry: TypeAlias = tuple[str, ReconstructionScopeValue]


@dataclass(frozen=True)
class PortfolioReconstructionScope:
    """Source scope that identifies a reconstructed portfolio state snapshot."""

    portfolio_id: str
    as_of_date: date
    valuation_date: date
    position_epoch: int
    cashflow_epoch: int
    product: str = "PortfolioStateSnapshot"
    restatement_version: str = CURRENT_RESTATEMENT_VERSION
    transaction_window_start: date | None = None
    transaction_window_end: date | None = None
    source_data_products: tuple[str, ...] = ()
    policy_version: str | None = None


@dataclass(frozen=True, slots=True)
class ProductReconstructionScope:
    """Canonical product scope used to bind runtime reconstruction evidence."""

    product: str
    portfolio_id: str
    as_of_date: date
    source_data_products: tuple[str, ...]
    restatement_version: str
    policy_version: str | None = None
    qualifiers: tuple[ReconstructionScopeEntry, ...] = ()
    material_evidence: tuple[ReconstructionScopeEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class ReconstructionScopeEvidence:
    """Stable identity and lineage fields for one canonical reconstruction scope."""

    scope_id: str
    scope_content_hash: str
    source_data_products: tuple[str, ...]
    restatement_version: str

    def lineage(self) -> dict[str, str]:
        """Return bounded string lineage suitable for framework response metadata."""

        return {
            "reconstruction_scope_version": RECONSTRUCTION_SCOPE_VERSION,
            "reconstruction_scope_id": self.scope_id,
            "reconstruction_scope_content_hash": self.scope_content_hash,
            "reconstruction_restatement_version": self.restatement_version,
            "reconstruction_source_data_products": json.dumps(
                self.source_data_products,
                separators=(",", ":"),
            ),
        }


def build_portfolio_snapshot_id(scope: PortfolioReconstructionScope) -> str:
    """Build a stable snapshot id from the full reconstruction source scope."""

    payload = _canonical_scope_payload(scope)
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{SNAPSHOT_ID_PREFIX}_{digest[:32]}"


def build_reconstruction_scope_evidence(
    scope: ProductReconstructionScope,
) -> ReconstructionScopeEvidence:
    """Build collision-safe identity and lineage for a product reconstruction scope."""

    payload = _canonical_product_scope_payload(scope)
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ReconstructionScopeEvidence(
        scope_id=f"{RECONSTRUCTION_SCOPE_ID_PREFIX}_{digest[:32]}",
        scope_content_hash=f"sha256:{digest}",
        source_data_products=tuple(sorted(set(scope.source_data_products))),
        restatement_version=scope.restatement_version,
    )


def _canonical_scope_payload(scope: PortfolioReconstructionScope) -> dict[str, object]:
    _validate_reconstruction_scope(scope)
    return {
        "as_of_date": scope.as_of_date.isoformat(),
        "cashflow_epoch": scope.cashflow_epoch,
        "policy_version": scope.policy_version,
        "portfolio_id": scope.portfolio_id,
        "position_epoch": scope.position_epoch,
        "product": scope.product,
        "restatement_version": scope.restatement_version,
        "source_data_products": sorted(set(scope.source_data_products)),
        "transaction_window_end": _date_or_none(scope.transaction_window_end),
        "transaction_window_start": _date_or_none(scope.transaction_window_start),
        "valuation_date": scope.valuation_date.isoformat(),
    }


def _canonical_product_scope_payload(scope: ProductReconstructionScope) -> dict[str, object]:
    _validate_product_reconstruction_scope(scope)
    return {
        "scope_version": RECONSTRUCTION_SCOPE_VERSION,
        "product": scope.product,
        "portfolio_id": scope.portfolio_id,
        "as_of_date": scope.as_of_date.isoformat(),
        "restatement_version": scope.restatement_version,
        "policy_version": scope.policy_version,
        "source_data_products": sorted(set(scope.source_data_products)),
        "qualifiers": _canonical_scope_entries(scope.qualifiers, "qualifiers"),
        "material_evidence": _canonical_scope_entries(
            scope.material_evidence,
            "material_evidence",
        ),
    }


def _validate_reconstruction_scope(scope: PortfolioReconstructionScope) -> None:
    _require_text(scope.portfolio_id, "portfolio_id")
    _require_text(scope.product, "product")
    _require_text(scope.restatement_version, "restatement_version")
    if scope.policy_version is not None:
        _require_text(scope.policy_version, "policy_version")
    _require_non_negative(scope.position_epoch, "position_epoch")
    _require_non_negative(scope.cashflow_epoch, "cashflow_epoch")
    _validate_transaction_window(scope)
    for source_data_product in scope.source_data_products:
        _require_text(source_data_product, "source_data_products")


def _validate_product_reconstruction_scope(scope: ProductReconstructionScope) -> None:
    _require_text(scope.product, "product")
    _require_text(scope.portfolio_id, "portfolio_id")
    _require_text(scope.restatement_version, "restatement_version")
    if scope.policy_version is not None:
        _require_text(scope.policy_version, "policy_version")
    if not scope.source_data_products:
        raise ValueError("source_data_products is required")
    for source_data_product in scope.source_data_products:
        _require_text(source_data_product, "source_data_products")


def _canonical_scope_entries(
    entries: tuple[ReconstructionScopeEntry, ...],
    field_name: str,
) -> dict[str, dict[str, object]]:
    canonical: dict[str, dict[str, object]] = {}
    for key, value in entries:
        _require_text(key, f"{field_name} key")
        if key in canonical:
            raise ValueError(f"{field_name} contains duplicate key: {key}")
        canonical[key] = _typed_scope_value(value, field_name=field_name, key=key)
    return canonical


def _typed_scope_value(
    value: ReconstructionScopeValue,
    *,
    field_name: str,
    key: str,
) -> dict[str, object]:
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name}.{key} datetime must be timezone-aware")
        return {
            "type": "datetime",
            "value": value.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, str):
        return {"type": "string", "value": value}
    raise TypeError(
        f"{field_name}.{key} must be a string, integer, boolean, date, datetime, or null"
    )


def _validate_transaction_window(scope: PortfolioReconstructionScope) -> None:
    if bool(scope.transaction_window_start) != bool(scope.transaction_window_end):
        raise ValueError(
            "transaction_window_start and transaction_window_end must be provided together"
        )
    if scope.transaction_window_start and scope.transaction_window_end:
        if scope.transaction_window_start > scope.transaction_window_end:
            raise ValueError("transaction_window_start must be on or before transaction_window_end")


def _date_or_none(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
