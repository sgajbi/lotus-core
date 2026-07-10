from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any

from .booked_transaction import BookedTransaction

TRANSACTION_SEMANTIC_IDENTITY_VERSION = "v1"
_NON_MATERIAL_FIELDS = frozenset({"created_at"})


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
        field.name: _canonical_value(getattr(transaction, field.name))
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
