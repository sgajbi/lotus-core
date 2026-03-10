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
        description="Normalized and validated sample rows for UI preview.",
        examples=[
            [
                {
                    "portfolioId": "PORT_001",
                    "baseCurrency": "USD",
                    "status": "Active",
                }
            ]
        ],
    )
    errors: list[UploadRowError] = Field(
        default_factory=list,
        description="Validation errors by row for correction before commit.",
        examples=[[{"row_number": 7, "message": "baseCurrency is required"}]],
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
