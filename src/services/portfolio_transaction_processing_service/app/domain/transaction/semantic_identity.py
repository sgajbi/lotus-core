"""Build deterministic semantic identities for booked transactions and corrections."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any

from .booked import BookedTransaction

TRANSACTION_SEMANTIC_IDENTITY_VERSION = "v1"
TRANSACTION_CORRECTION_IDENTITY_VERSION = "v1"
_PROCESSOR_OWNED_OUTPUT_FIELDS = frozenset(
    {
        "allocated_cost_basis_base",
        "allocated_cost_basis_local",
        "gross_cost",
        "net_cost",
        "net_cost_local",
        "realized_capital_pnl_base",
        "realized_capital_pnl_local",
        "realized_fx_pnl_base",
        "realized_fx_pnl_local",
        "realized_gain_loss",
        "realized_gain_loss_local",
        "realized_total_pnl_base",
        "realized_total_pnl_local",
        "transaction_fx_rate",
    }
)
_NON_MATERIAL_FIELDS = _PROCESSOR_OWNED_OUTPUT_FIELDS | {"created_at"}
_DEFAULT_POLICY_IDS_BY_FAMILY = {
    "BUY": frozenset({"BUY_DEFAULT_POLICY"}),
    "DIVIDEND": frozenset({"DIVIDEND_DEFAULT_POLICY"}),
    "FX": frozenset({"FX_DEFAULT_POLICY"}),
    "INTEREST": frozenset({"INTEREST_DEFAULT_POLICY"}),
    "SELL": frozenset({"SELL_AVCO_POLICY", "SELL_FIFO_POLICY"}),
}
_DEFAULT_POLICY_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class TransactionSemanticIdentity:
    semantic_key: str
    payload_fingerprint: str


def build_transaction_semantic_identity(
    transaction: BookedTransaction,
) -> TransactionSemanticIdentity:
    semantic_key = ":".join(
        (
            "transaction-processing",
            TRANSACTION_SEMANTIC_IDENTITY_VERSION,
            transaction.portfolio_id.strip(),
            transaction.transaction_id.strip(),
            str(transaction.epoch or 0),
        )
    )
    material_payload = {
        field.name: _canonical_transaction_field(transaction, field.name)
        for field in fields(transaction)
        if field.name not in _NON_MATERIAL_FIELDS
    }
    canonical_payload = json.dumps(
        material_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    payload_fingerprint = "sha256:" + sha256(canonical_payload.encode("utf-8")).hexdigest()
    return TransactionSemanticIdentity(
        semantic_key=semantic_key,
        payload_fingerprint=payload_fingerprint,
    )


def build_transaction_correction_identity(
    transaction: BookedTransaction,
) -> TransactionSemanticIdentity:
    """Build an immutable identity for one explicit canonical correction payload."""

    base_identity = build_transaction_semantic_identity(transaction)
    semantic_key = ":".join(
        (
            "transaction-correction",
            TRANSACTION_CORRECTION_IDENTITY_VERSION,
            transaction.portfolio_id.strip(),
            transaction.transaction_id.strip(),
            str(transaction.epoch or 0),
            base_identity.payload_fingerprint,
        )
    )
    return TransactionSemanticIdentity(
        semantic_key=semantic_key,
        payload_fingerprint=base_identity.payload_fingerprint,
    )


def _canonical_transaction_field(transaction: BookedTransaction, field_name: str) -> Any:
    value = getattr(transaction, field_name)
    family = _transaction_family(transaction.transaction_type)
    if field_name == "economic_event_id":
        generated = f"EVT-{family}-{transaction.portfolio_id}-{transaction.transaction_id}"
        if value is None or value == generated:
            return None
    elif field_name == "linked_transaction_group_id":
        generated = f"LTG-{family}-{transaction.portfolio_id}-{transaction.transaction_id}"
        if value is None or value == generated:
            return None
    elif field_name == "calculation_policy_id":
        if value is None or value in _DEFAULT_POLICY_IDS_BY_FAMILY.get(family, ()):
            return None
    elif field_name == "calculation_policy_version":
        if family in _DEFAULT_POLICY_IDS_BY_FAMILY and (
            value is None or value == _DEFAULT_POLICY_VERSION
        ):
            return None
    elif field_name == "external_cash_transaction_id":
        generated = f"{transaction.transaction_id}-CASHLEG"
        if transaction.cash_entry_mode == "AUTO_GENERATE" and (value is None or value == generated):
            return None
    return _canonical_value(value)


def _transaction_family(transaction_type: str) -> str:
    normalized = transaction_type.strip().upper()
    if normalized.startswith("FX_"):
        return "FX"
    return normalized


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        normalized = value
        if normalized.tzinfo is not None:
            normalized = normalized.astimezone(timezone.utc).replace(tzinfo=None)
        return normalized.isoformat(timespec="microseconds") + "Z"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    return value
