"""Bounded source batch identity, independent of response content and membership."""

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .ingestion_evidence import SourceBatchIdentityScope, build_source_batch_fingerprint


class TransactionBatchLineage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_system: str | None = None
    source_batch_id: str | None = None
    reason: Literal["PROVEN", "LEGACY_UNKNOWN", "MIXED_BATCHES", "EMPTY_WINDOW"]

    @model_validator(mode="after")
    def require_consistent_batch_scope(self) -> "TransactionBatchLineage":
        identifiers = (self.source_system, self.source_batch_id)
        if self.reason == "PROVEN":
            if not all(
                isinstance(value, str) and value.strip() == value and value for value in identifiers
            ):
                raise ValueError("Proven batch lineage requires exact nonblank supplier scope")
        elif any(value is not None for value in identifiers):
            raise ValueError("Unavailable batch lineage cannot carry an asserted supplier scope")
        return self

    def fingerprint(self, *, tenant_id: str) -> str | None:
        if self.reason != "PROVEN" or not self.source_system or not self.source_batch_id:
            return None
        return build_source_batch_fingerprint(
            SourceBatchIdentityScope(
                source_system=self.source_system,
                source_batch_id=self.source_batch_id,
                tenant_id=tenant_id,
                payload_kind="transaction",
            )
        )

    def lineage(self) -> dict[str, str]:
        fields = {
            "batch_lineage_scope": "transactions",
            "batch_lineage_status": "PROVEN" if self.reason == "PROVEN" else "UNAVAILABLE",
            "batch_lineage_reason": self.reason,
        }
        if self.reason == "PROVEN" and self.source_system and self.source_batch_id:
            fields.update(source_system=self.source_system, source_batch_id=self.source_batch_id)
        return fields


def transaction_batch_lineage_from_counts(
    *,
    count: int,
    complete_count: int,
    scope_count: int,
    source_system: str | None,
    source_batch_id: str | None,
) -> TransactionBatchLineage:
    if not count:
        return TransactionBatchLineage(reason="EMPTY_WINDOW")
    if scope_count > 1:
        return TransactionBatchLineage(reason="MIXED_BATCHES")
    if complete_count != count or scope_count != 1 or not source_system or not source_batch_id:
        return TransactionBatchLineage(reason="LEGACY_UNKNOWN")
    return TransactionBatchLineage(
        source_system=source_system, source_batch_id=source_batch_id, reason="PROVEN"
    )


def transaction_batch_lineage_from_payload(payload: Mapping[str, Any]) -> TransactionBatchLineage:
    records = payload.get("transactions")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        return TransactionBatchLineage(reason="LEGACY_UNKNOWN")
    scopes: set[tuple[str, str]] = set()
    complete = 0
    for record in records:
        if not isinstance(record, Mapping):
            continue
        system, batch = record.get("source_system"), record.get("source_batch_id")
        if isinstance(system, str) and system.strip() and isinstance(batch, str) and batch.strip():
            scopes.add((system, batch))
            complete += 1
    system, batch = next(iter(scopes), (None, None))
    return transaction_batch_lineage_from_counts(
        count=len(records),
        complete_count=complete,
        scope_count=len(scopes),
        source_system=system,
        source_batch_id=batch,
    )
