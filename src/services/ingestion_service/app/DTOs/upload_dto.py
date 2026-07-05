from typing import Any, Literal

from pydantic import BaseModel, Field

UploadEntityType = Literal[
    "portfolios",
    "instruments",
    "transactions",
    "market_prices",
    "fx_rates",
    "business_dates",
]


class UploadRowError(BaseModel):
    row_number: int = Field(
        ...,
        description="1-based row number from the uploaded file.",
        examples=[7],
    )
    message: str = Field(
        ...,
        description="Validation error message for the row.",
        examples=["baseCurrency is required"],
    )
    code: str = Field(
        "SCHEMA_VALIDATION_FAILED",
        description="Stable machine-readable ingestion validation code.",
        examples=["INVALID_EFFECTIVE_WINDOW"],
    )
    severity: Literal["error", "warning"] = Field(
        "error",
        description="Validation severity used by operators and upstream systems.",
        examples=["error"],
    )
    field_path: str | None = Field(
        None,
        description="Canonical field path when the validation failure maps to a specific field.",
        examples=["effective_to"],
    )
    record_key: str | None = Field(
        None,
        description="Source-safe row key derived from stable identifiers in the submitted row.",
        examples=["source_record_id:tax-rule-2026-001"],
    )
    remediation: str | None = Field(
        None,
        description="Safe remediation hint for correcting the validation failure.",
        examples=["Use an effective_to date that is not earlier than effective_from."],
    )
    source_lineage: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Source-safe lineage fields submitted with the row, limited to source_system, "
            "source_record_id, observed_at, and source_batch_id."
        ),
        examples=[
            {
                "source_system": "tax-reference",
                "source_record_id": "tax-rule-2026-001",
                "observed_at": "2026-01-31T23:00:00Z",
            }
        ],
    )


class UploadPreviewResponse(BaseModel):
    entity_type: UploadEntityType = Field(
        ...,
        description="Entity family resolved from the upload target.",
        examples=["portfolios"],
    )
    file_format: Literal["csv", "xlsx"] = Field(
        ...,
        description="Detected upload file format.",
        examples=["csv"],
    )
    total_rows: int = Field(
        ...,
        description="Total row count parsed from the uploaded file.",
        examples=[25],
    )
    valid_rows: int = Field(
        ...,
        description="Count of rows that passed schema validation.",
        examples=[23],
    )
    invalid_rows: int = Field(
        ...,
        description="Count of rows that failed validation.",
        examples=[2],
    )
    sample_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Redacted valid sample rows returned only when include_sample_rows=true and the "
            "caller has the signed preview-sample capability. Defaults to an empty list."
        ),
        examples=[
            [
                {
                    "portfolioId": "***REDACTED***",
                    "baseCurrency": "USD",
                    "status": "Active",
                }
            ]
        ],
    )
    errors: list[UploadRowError] = Field(
        default_factory=list,
        description=(
            "Validation errors by row for correction before commit. Each error includes the "
            "legacy message plus a stable validation code, severity, field path, record key, "
            "remediation hint, and safe source lineage when available."
        ),
        examples=[
            [
                {
                    "row_number": 7,
                    "message": "effective_to: effective_to must be on or after effective_from",
                    "code": "INVALID_EFFECTIVE_WINDOW",
                    "severity": "error",
                    "field_path": "effective_to",
                    "record_key": "source_record_id:tax-rule-2026-001",
                }
            ]
        ],
    )


class UploadCommitResponse(BaseModel):
    entity_type: UploadEntityType = Field(
        ...,
        description="Entity family resolved from the upload target.",
        examples=["transactions"],
    )
    file_format: Literal["csv", "xlsx"] = Field(
        ...,
        description="Detected upload file format.",
        examples=["xlsx"],
    )
    total_rows: int = Field(
        ...,
        description="Total row count parsed from the uploaded file.",
        examples=[120],
    )
    valid_rows: int = Field(
        ...,
        description="Count of rows that passed validation checks.",
        examples=[118],
    )
    invalid_rows: int = Field(
        ...,
        description="Count of rows rejected during validation.",
        examples=[2],
    )
    published_rows: int = Field(
        ...,
        description="Count of rows published to canonical ingestion topics.",
        examples=[118],
    )
    skipped_rows: int = Field(
        ...,
        description="Count of rows skipped because partial commit was allowed.",
        examples=[2],
    )
    message: str = Field(
        ...,
        description="Human-readable commit summary returned to the caller.",
        examples=["Committed 118 transaction rows; skipped 2 invalid rows."],
    )
