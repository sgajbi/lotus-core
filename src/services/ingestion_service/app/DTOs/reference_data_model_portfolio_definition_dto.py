from __future__ import annotations

from datetime import date, datetime
from typing import Literal, cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ModelPortfolioDefinitionIngestionRequest(BaseModel):
    model_portfolios: list[ModelPortfolioDefinitionRecord] = Field(
        ...,
        description="Model portfolio definition records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
                    "model_portfolio_version": "2026.03",
                    "display_name": "Singapore Balanced DPM Model",
                    "base_currency": "SGD",
                    "risk_profile": "balanced",
                    "mandate_type": "discretionary",
                    "rebalance_frequency": "monthly",
                    "approval_status": "approved",
                    "effective_from": "2026-03-25",
                }
            ]
        ],
    )

    model_config = ConfigDict()
