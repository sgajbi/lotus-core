from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
        _validate_target_band_order(
            target_weight=self.target_weight,
            min_weight=self.min_weight,
            max_weight=self.max_weight,
        )
        return self

    model_config = ConfigDict()


def _validate_target_band_order(
    *,
    target_weight: Decimal,
    min_weight: Decimal | None,
    max_weight: Decimal | None,
) -> None:
    if min_weight is not None and min_weight > target_weight:
        raise ValueError("min_weight must be less than or equal to target_weight")
    if max_weight is not None and max_weight < target_weight:
        raise ValueError("max_weight must be greater than or equal to target_weight")


class ModelPortfolioTargetIngestionRequest(BaseModel):
    model_portfolio_targets: list[ModelPortfolioTargetRecord] = Field(
        ...,
        description="Model portfolio target records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
                    "model_portfolio_version": "2026.03",
                    "instrument_id": "EQ_US_AAPL",
                    "target_weight": "0.1200000000",
                    "min_weight": "0.0800000000",
                    "max_weight": "0.1600000000",
                    "target_status": "active",
                    "effective_from": "2026-03-25",
                }
            ]
        ],
    )

    @model_validator(mode="after")
    def validate_target_uniqueness(self) -> "ModelPortfolioTargetIngestionRequest":
        keys = [
            (
                target.model_portfolio_id,
                target.model_portfolio_version,
                target.instrument_id,
                target.effective_from,
            )
            for target in self.model_portfolio_targets
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("model_portfolio_targets contains duplicate target records")
        return self

    model_config = ConfigDict()
