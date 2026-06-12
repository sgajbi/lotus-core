from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ModelPortfolioDefinitionRecord(BaseModel):
    model_portfolio_id: str = Field(
        ...,
        description="Canonical model portfolio identifier.",
        examples=["MODEL_SG_BALANCED_DPM"],
    )
    model_portfolio_version: str = Field(
        ...,
        description="Approved model portfolio version.",
        examples=["2026.03"],
    )
    display_name: str = Field(
        ...,
        description="Business display name for the model portfolio.",
        examples=["Singapore Balanced DPM Model"],
    )
    base_currency: str = Field(
        ...,
        description=(
            "Canonical three-letter model base currency used for target model, rebalancing, "
            "mandate, and benchmark-alignment calculations."
        ),
        examples=["SGD"],
    )
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
        None,
        description="Expected rebalance cadence.",
        examples=["monthly"],
    )
    approval_status: Literal["approved", "draft", "retired", "suspended"] = Field(
        "approved",
        description="Model approval lifecycle status.",
        examples=["approved"],
    )
    approved_at: datetime | None = Field(
        None,
        description="Timestamp at which the model version was approved.",
        examples=["2026-03-20T09:00:00Z"],
    )
    effective_from: date = Field(
        ...,
        description="Model version effective start date.",
        examples=["2026-03-25"],
    )
    effective_to: date | None = Field(
        None,
        description="Model version effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream model portfolio source system.",
        examples=["investment_office_model_system"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["model_sg_balanced_202603"],
    )
    observed_at: datetime | None = Field(
        None,
        description=(
            "Timestamp when the upstream source observed or published the model definition."
        ),
        examples=["2026-03-20T09:00:00Z"],
    )
    quality_status: str = Field(
        "accepted",
        description="Data quality status for the model definition.",
        examples=["accepted"],
    )

    @field_validator("base_currency", mode="before")
    @classmethod
    def _normalize_base_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class ModelPortfolioTargetRecord(BaseModel):
    model_portfolio_id: str = Field(
        ...,
        description="Canonical model portfolio identifier.",
        examples=["MODEL_SG_BALANCED_DPM"],
    )
    model_portfolio_version: str = Field(
        ...,
        description="Approved model portfolio version.",
        examples=["2026.03"],
    )
    instrument_id: str = Field(
        ...,
        description="Canonical instrument identifier.",
        examples=["EQ_US_AAPL"],
    )
    target_weight: Decimal = Field(
        ...,
        ge=Decimal(0),
        le=Decimal(1),
        description="Target instrument weight as a decimal ratio between 0 and 1.",
        examples=["0.1200000000"],
    )
    min_weight: Decimal | None = Field(
        None,
        ge=Decimal(0),
        le=Decimal(1),
        description="Optional minimum policy band for the instrument.",
        examples=["0.0800000000"],
    )
    max_weight: Decimal | None = Field(
        None,
        ge=Decimal(0),
        le=Decimal(1),
        description="Optional maximum policy band for the instrument.",
        examples=["0.1600000000"],
    )
    target_status: Literal["active", "inactive"] = Field(
        "active",
        description="Target lifecycle status.",
        examples=["active"],
    )
    effective_from: date = Field(
        ...,
        description="Target effective start date.",
        examples=["2026-03-25"],
    )
    effective_to: date | None = Field(
        None,
        description="Target effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream model target source system.",
        examples=["investment_office_model_system"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["model_sg_balanced_202603_eq_us_aapl"],
    )
    observed_at: datetime | None = Field(
        None,
        description="Timestamp when the upstream source observed or published the model target.",
        examples=["2026-03-20T09:00:00Z"],
    )
    quality_status: str = Field(
        "accepted",
        description="Data quality status for the model target.",
        examples=["accepted"],
    )

    @model_validator(mode="after")
    def validate_bands(self) -> "ModelPortfolioTargetRecord":
        if self.min_weight is not None and self.min_weight > self.target_weight:
            raise ValueError("min_weight must be less than or equal to target_weight")
        if self.max_weight is not None and self.max_weight < self.target_weight:
            raise ValueError("max_weight must be greater than or equal to target_weight")
        return self

    model_config = ConfigDict()
