"""Public contracts for the DPM model portfolio target source product."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class ModelPortfolioTargetRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the approved model target version.",
        examples=["2026-03-25"],
    )
    include_inactive_targets: bool = Field(
        False,
        description=(
            "Include inactive target rows when true. Default false returns only active approved "
            "model target rows."
        ),
        examples=[False],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetRow(BaseModel):
    instrument_id: str = Field(
        ...,
        description="Canonical instrument identifier in the model target universe.",
        examples=["EQ_US_AAPL"],
    )
    target_weight: Decimal = Field(
        ...,
        description="Target instrument weight as a decimal ratio between 0 and 1.",
        examples=["0.1200000000"],
    )
    min_weight: Decimal | None = Field(
        None,
        description="Optional minimum target band as a decimal ratio.",
        examples=["0.0800000000"],
    )
    max_weight: Decimal | None = Field(
        None,
        description="Optional maximum target band as a decimal ratio.",
        examples=["0.1600000000"],
    )
    target_status: str = Field(
        ...,
        description="Target lifecycle status from the model source system.",
        examples=["active"],
    )
    quality_status: str = Field(
        ...,
        description="Data quality status for this target row.",
        examples=["accepted"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["model_sg_balanced_202603_eq_us_aapl"],
    )

    model_config = ConfigDict()


class ModelPortfolioSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for the resolved model target product.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code explaining model target readiness.",
        examples=["MODEL_TARGETS_READY"],
    )
    target_count: int = Field(
        ...,
        description="Number of target rows returned after request filtering.",
        examples=[7],
    )
    total_target_weight: Decimal = Field(
        ...,
        description="Sum of returned target weights as a decimal ratio.",
        examples=["1.0000000000"],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DpmModelPortfolioTarget"] = product_name_field("DpmModelPortfolioTarget")
    product_version: Literal["v1"] = product_version_field()
    model_portfolio_id: str = Field(
        ...,
        description="Canonical model portfolio identifier.",
        examples=["MODEL_SG_BALANCED_DPM"],
    )
    model_portfolio_version: str = Field(
        ...,
        description="Approved model portfolio version resolved for the as-of date.",
        examples=["2026.03"],
    )
    display_name: str = Field(
        ...,
        description="Business display name for the model portfolio.",
        examples=["Singapore Balanced DPM Model"],
    )
    base_currency: str = Field(..., description="Model base currency.", examples=["SGD"])
    risk_profile: str = Field(
        ...,
        description="Mandate risk profile aligned to this model.",
        examples=["balanced"],
    )
    mandate_type: str = Field(
        ...,
        description="Mandate type for which this model is approved.",
        examples=["discretionary"],
    )
    rebalance_frequency: str | None = Field(
        None, description="Expected rebalance cadence.", examples=["monthly"]
    )
    approval_status: str = Field(
        ...,
        description="Approval lifecycle status for the resolved model version.",
        examples=["approved"],
    )
    approved_at: datetime | None = Field(
        None,
        description="Timestamp when the resolved model version was approved.",
        examples=["2026-03-20T09:00:00Z"],
    )
    effective_from: date = Field(
        ...,
        description="Resolved model version effective start date.",
        examples=["2026-03-25"],
    )
    effective_to: date | None = Field(
        None,
        description="Resolved model version effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    targets: list[ModelPortfolioTargetRow] = Field(
        ...,
        description="Deterministically ordered target rows for the resolved model version.",
    )
    supportability: ModelPortfolioSupportability = Field(
        ...,
        description="Readiness and completeness diagnostics for model target consumption.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage metadata for audit, replay, and downstream diagnostics.",
        examples=[
            {
                "source_system": "investment_office_model_system",
                "source_record_id": "model_sg_balanced_202603",
                "contract_version": "rfc_087_v1",
            }
        ],
    )

    model_config = ConfigDict()
