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

    def as_dict(self) -> dict[str, Any]:
        return {"row_number": self.row_number, "message": self.message}


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
