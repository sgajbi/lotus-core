from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

UploadEntity = Literal[
    "portfolios",
    "instruments",
    "transactions",
    "market_prices",
    "fx_rates",
    "business_dates",
]


@dataclass(frozen=True, slots=True)
class UploadPreviewCommand:
    entity_type: UploadEntity
    filename: str
    content: bytes
    sample_size: int = 20
    include_sample_rows: bool = False


@dataclass(frozen=True, slots=True)
class UploadCommitCommand:
    entity_type: UploadEntity
    filename: str
    content: bytes
    allow_partial: bool


@dataclass(frozen=True, slots=True)
class UploadRowIssue:
    row_number: int
    message: str
    code: str = "SCHEMA_VALIDATION_FAILED"
    severity: str = "error"
    field_path: str | None = None
    record_key: str | None = None
    remediation: str | None = None
    source_lineage: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "row_number": self.row_number,
            "message": self.message,
            "code": self.code,
            "severity": self.severity,
        }
        if self.field_path:
            payload["field_path"] = self.field_path
        if self.record_key:
            payload["record_key"] = self.record_key
        if self.remediation:
            payload["remediation"] = self.remediation
        if self.source_lineage:
            payload["source_lineage"] = dict(self.source_lineage)
        return payload


@dataclass(frozen=True, slots=True)
class UploadPreviewResult:
    entity_type: UploadEntity
    file_format: Literal["csv", "xlsx"]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[UploadRowIssue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class UploadCommitResult:
    entity_type: UploadEntity
    file_format: Literal["csv", "xlsx"]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    published_rows: int
    skipped_rows: int
    message: str
