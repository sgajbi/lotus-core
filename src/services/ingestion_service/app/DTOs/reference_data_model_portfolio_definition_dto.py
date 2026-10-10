from __future__ import annotations

from datetime import date, datetime
from typing import Literal, cast

from portfolio_common.domain.currency import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .ingestion_validation_errors import validate_effective_window, validate_unique_records
from .reference_data_source_observation_dto import SourceObservationLineage


class ModelPortfolioDefinitionRecord(SourceObservationLineage):
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
        description=(
            "Inclusive model version end date, null when open-ended. Must be on or after "
            "effective_from; equal dates form a valid one-day window."
        ),
        examples=["2026-12-31", "2026-03-25", None],
    )

    @field_validator("base_currency", mode="before")
    @classmethod
    def _normalize_base_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    @model_validator(mode="after")
    def validate_window(self) -> "ModelPortfolioDefinitionRecord":
        validate_effective_window(
            effective_from=self.effective_from, effective_to=self.effective_to
        )
        return self

    model_config = ConfigDict()


class ModelPortfolioDefinitionIngestionRequest(BaseModel):
    model_portfolios: list[ModelPortfolioDefinitionRecord] = Field(
        ...,
        description=(
            "Model portfolio definition records to ingest or upsert. Each "
            "(model_portfolio_id, model_portfolio_version, effective_from) identity must "
            "occur once per request. Identical or conflicting duplicates reject the entire "
            "batch with HTTP 422 DUPLICATE_SOURCE_KEY before job creation or persistence; "
            "request idempotency is a separate concern."
        ),
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

    @model_validator(mode="after")
    def validate_definition_uniqueness(self) -> "ModelPortfolioDefinitionIngestionRequest":
        validate_unique_records(
            (
                (record.model_portfolio_id, record.model_portfolio_version, record.effective_from)
                for record in self.model_portfolios
            ),
            field_path="model_portfolios",
        )
        return self

    model_config = ConfigDict()
