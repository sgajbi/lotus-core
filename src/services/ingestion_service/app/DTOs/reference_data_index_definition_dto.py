from __future__ import annotations

from datetime import date, datetime
from typing import cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator


class IndexDefinitionRecord(BaseModel):
    index_id: str = Field(
        ..., description="Canonical index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    index_name: str = Field(
        ..., description="Index display name.", examples=["MSCI World Total Return"]
    )
    index_currency: str = Field(
        ...,
        description=(
            "Canonical three-letter index currency used for benchmark construction, "
            "performance comparison, and reporting alignment."
        ),
        examples=["USD"],
    )
    index_type: str | None = Field(
        None, description="Index type descriptor.", examples=["equity_index"]
    )
    index_status: str = Field("active", description="Index status.", examples=["active"])
    index_provider: str | None = Field(None, description="Index provider.", examples=["MSCI"])
    index_market: str | None = Field(
        None,
        description="Index market or universe scope.",
        examples=["global_developed"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Canonical classification labels for attribution.",
        examples=[{"asset_class": "equity", "sector": "technology", "region": "global"}],
    )
    effective_from: date = Field(
        ..., description="Definition effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None, description="Definition effective end date.", examples=["2026-12-31"]
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the index definition payload.",
        examples=["2026-01-31T23:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["idx_v20260131"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("index_currency", mode="before")
    @classmethod
    def _normalize_index_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class IndexDefinitionIngestionRequest(BaseModel):
    indices: list[IndexDefinitionRecord] = Field(
        ...,
        description="Index definition records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "index_name": "MSCI World Total Return",
                    "index_currency": "USD",
                    "effective_from": "2025-01-01",
                }
            ]
        ],
    )

    model_config = ConfigDict()
