"""Deterministic identity helpers for RFC-0083 portfolio reconstruction scopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from hashlib import sha256


SNAPSHOT_ID_PREFIX = "pss"
CURRENT_RESTATEMENT_VERSION = "current"


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


def build_portfolio_snapshot_id(scope: PortfolioReconstructionScope) -> str:
    """Build a stable snapshot id from the full reconstruction source scope."""

    payload = _canonical_scope_payload(scope)
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{SNAPSHOT_ID_PREFIX}_{digest[:32]}"


def _canonical_scope_payload(scope: PortfolioReconstructionScope) -> dict[str, object]:
    _require_text(scope.portfolio_id, "portfolio_id")
    _require_text(scope.product, "product")
    _require_text(scope.restatement_version, "restatement_version")
    if scope.policy_version is not None:
        _require_text(scope.policy_version, "policy_version")
    _require_non_negative(scope.position_epoch, "position_epoch")
    _require_non_negative(scope.cashflow_epoch, "cashflow_epoch")
    if bool(scope.transaction_window_start) != bool(scope.transaction_window_end):
        raise ValueError(
            "transaction_window_start and transaction_window_end must be provided together"
        )
    if scope.transaction_window_start and scope.transaction_window_end:
        if scope.transaction_window_start > scope.transaction_window_end:
            raise ValueError("transaction_window_start must be on or before transaction_window_end")
    for source_data_product in scope.source_data_products:
        _require_text(source_data_product, "source_data_products")

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


def _date_or_none(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
