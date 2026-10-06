"""Detached immutable source authority; no ORM identity or session crosses this seam."""

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import cast


def freeze_source_value(value: object) -> object:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Source snapshot keys must be strings")
        return MappingProxyType({key: freeze_source_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_source_value(item) for item in value)
    if value is None or isinstance(value, (str, int, bool, float, Decimal, date, datetime)):
        return value
    raise TypeError("Source snapshot contains an unsupported value")


def source_value_material(value: object) -> object:
    """Return a fresh ordinary material projection, retaining JSON list semantics."""
    if isinstance(value, Mapping):
        return {key: source_value_material(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [source_value_material(item) for item in value]
    return value


class SourceInputRejected(ValueError):
    """Boundary validation failed without exposing framework exceptions or payloads."""


@dataclass(frozen=True, slots=True)
class SourceRevisionFact:
    revision_id: str
    tenant_id: str
    portfolio_id: str
    transaction_id: str
    root_raw_event_id: int
    source_local: Decimal
    source_base: Decimal
    root_raw_sha256: str
    predecessor_revision_id: str | None
    expected_head_id: str
    expected_head_sha256: str
    command_id: str
    operation_id: str
    canonical_request_sha256: str
    attestation_sha256: str
    original_output_sha256: str
    revision_sha256: str
    original_local_present: bool
    original_base_present: bool
    qualification_receipt: Mapping[str, object]
    authorization_claims: Mapping[str, object]
    reason: str
    correlation_id: str
    trace_id: str
    confirmed_at: datetime

    def __post_init__(self) -> None:
        for name in ("qualification_receipt", "authorization_claims"):
            object.__setattr__(self, name, freeze_source_value(getattr(self, name)))

    def material(self) -> dict[str, object]:
        return {
            field.name: source_value_material(getattr(self, field.name)) for field in fields(self)
        }

    @classmethod
    def from_material(cls, material: Mapping[str, object]) -> "SourceRevisionFact":
        if set(material) != {field.name for field in fields(cls)}:
            raise ValueError("Source revision fact schema differs from complete material")
        return cls(
            revision_id=cast(str, material["revision_id"]),
            tenant_id=cast(str, material["tenant_id"]),
            portfolio_id=cast(str, material["portfolio_id"]),
            transaction_id=cast(str, material["transaction_id"]),
            root_raw_event_id=cast(int, material["root_raw_event_id"]),
            source_local=cast(Decimal, material["source_local"]),
            source_base=cast(Decimal, material["source_base"]),
            root_raw_sha256=cast(str, material["root_raw_sha256"]),
            predecessor_revision_id=cast(str | None, material["predecessor_revision_id"]),
            expected_head_id=cast(str, material["expected_head_id"]),
            expected_head_sha256=cast(str, material["expected_head_sha256"]),
            command_id=cast(str, material["command_id"]),
            operation_id=cast(str, material["operation_id"]),
            canonical_request_sha256=cast(str, material["canonical_request_sha256"]),
            attestation_sha256=cast(str, material["attestation_sha256"]),
            original_output_sha256=cast(str, material["original_output_sha256"]),
            revision_sha256=cast(str, material["revision_sha256"]),
            original_local_present=cast(bool, material["original_local_present"]),
            original_base_present=cast(bool, material["original_base_present"]),
            qualification_receipt=cast(Mapping[str, object], material["qualification_receipt"]),
            authorization_claims=cast(Mapping[str, object], material["authorization_claims"]),
            reason=cast(str, material["reason"]),
            correlation_id=cast(str, material["correlation_id"]),
            trace_id=cast(str, material["trace_id"]),
            confirmed_at=cast(datetime, material["confirmed_at"]),
        )


@dataclass(frozen=True, slots=True)
class RetainedTransactionSnapshot:
    portfolio_id: str
    transaction_id: str
    ledger_output: Mapping[str, object]
    stored_fingerprint: str | None
    original_receipt: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "ledger_output", freeze_source_value(self.ledger_output))
        object.__setattr__(self, "original_receipt", freeze_source_value(self.original_receipt))

    def output_material(self) -> dict[str, object]:
        return cast(dict[str, object], source_value_material(self.ledger_output))

    def receipt_material(self) -> object:
        return source_value_material(self.original_receipt)


@dataclass(frozen=True, slots=True)
class RawSourceSnapshot:
    id: int
    payload: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_source_value(self.payload))

    def payload_material(self) -> object:
        return source_value_material(self.payload)


@dataclass(frozen=True, slots=True)
class SourceOperationIntent:
    payload: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_source_value(self.payload))

    def payload_material(self) -> object:
        return source_value_material(self.payload)


@dataclass(frozen=True, slots=True)
class RetainedSourceRows:
    transaction: RetainedTransactionSnapshot
    raw_event: RawSourceSnapshot
    head: SourceRevisionFact | None
