"""Public contracts for the effective index definition catalog."""

from datetime import date, datetime
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class IndexCatalogRequest(BaseModel):
    """Filters for effective index master records."""

    as_of_date: date = Field(
        ..., description="Point-in-time date for index catalog retrieval.", examples=["2026-01-31"]
    )
    index_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional targeted index identifiers to resolve. Use this when the caller already "
            "knows the component universe and needs canonical metadata without scanning the full "
            "effective catalog."
        ),
        examples=[["IDX_MSCI_WORLD_TR", "IDX_BLOOMBERG_GLOBAL_AGG_TR"]],
    )
    index_currency: str | None = Field(
        None, description="Optional index currency filter.", examples=["USD"]
    )
    index_type: str | None = Field(
        None, description="Optional index type filter.", examples=["equity_index"]
    )
    index_status: str | None = Field(
        None, description="Optional index status filter.", examples=["active"]
    )

    model_config = ConfigDict()


class IndexDefinitionResponse(BaseModel):
    """One effective index master in the catalog."""

    index_id: str = Field(
        ..., description="Canonical index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    index_name: str = Field(
        ..., description="Index display name.", examples=["MSCI World Total Return"]
    )
    index_currency: str = Field(..., description="Index currency.", examples=["USD"])
    index_type: str | None = Field(
        None, description="Index type descriptor.", examples=["equity_index"]
    )
    index_status: str = Field(..., description="Index lifecycle status.", examples=["active"])
    index_provider: str | None = Field(None, description="Index data provider.", examples=["MSCI"])
    index_market: str | None = Field(
        None, description="Primary market or index universe.", examples=["global_developed"]
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Canonical index classification labels required for attribution and benchmark "
            "exposure grouping. Broad benchmark component indices can carry governed "
            "broad-market sector labels rather than issuer sectors."
        ),
        examples=[{"asset_class": "equity", "sector": "broad_market_equity", "region": "global"}],
    )
    effective_from: date = Field(
        ..., description="Definition effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None, description="Definition effective end date.", examples=["2026-12-31"]
    )
    quality_status: str = Field(..., description="Data quality status.", examples=["accepted"])
    source_timestamp: datetime | None = Field(
        None, description="Source publication timestamp.", examples=["2026-01-31T08:00:00Z"]
    )
    source_vendor: str | None = Field(None, description="Source vendor name.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for replay.",
        examples=["idx_world_tr_v20260131"],
    )

    model_config = ConfigDict()


class IndexCatalogResponse(SourceDataProductRuntimeMetadata):
    """Effective index catalog with collection-level source proof."""

    product_name: Literal["IndexDefinition"] = product_name_field("IndexDefinition")
    product_version: Literal["v1"] = product_version_field()
    records: list[IndexDefinitionResponse] = Field(
        default_factory=list,
        description="Index definition records effective for the requested date.",
        examples=[[{"index_id": "IDX_MSCI_WORLD_TR", "index_currency": "USD"}]],
    )
    record_count: int = Field(
        ..., description="Number of effective index records returned.", examples=[24]
    )
    completeness_status: Literal["COMPLETE", "PARTIAL", "EMPTY"] = Field(
        ...,
        description="Aggregate source quality posture across returned records.",
        examples=["COMPLETE"],
    )

    model_config = ConfigDict()
