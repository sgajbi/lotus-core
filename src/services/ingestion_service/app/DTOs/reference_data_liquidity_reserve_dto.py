from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LiquidityReserveRequirementRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the reserve requirement.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the reserve requirement.")
    mandate_id: str | None = Field(
        None, description="Mandate identifier when requirement-specific."
    )
    reserve_requirement_id: str = Field(..., description="Source-owned reserve requirement id.")
    reserve_type: Literal[
        "MIN_CASH_BUFFER", "SPENDING_RESERVE", "LIQUIDITY_BUCKET", "POLICY_MINIMUM", "OTHER"
    ] = Field(..., description="Bounded reserve requirement type.")
    reserve_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Reserve requirement lifecycle status."
    )
    required_amount: Decimal = Field(
        ..., gt=Decimal(0), description="Required reserve amount supplied by the source."
    )
    currency: str = Field(
        ...,
        description=(
            "Canonical three-letter currency for the reserve amount used by liquidity and "
            "policy-compliance calculations."
        ),
    )
    horizon_days: int = Field(..., ge=0)
    priority: int = Field(1, ge=1)
    policy_source: str = Field(..., description="Source policy or bank reference for requirement.")
    effective_from: date = Field(..., description="Requirement effective start date.")
    effective_to: date | None = Field(None, description="Requirement effective end date.")
    requirement_version: int = Field(1, ge=1)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    @model_validator(mode="after")
    def validate_requirement(self) -> "LiquidityReserveRequirementRecord":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self

    model_config = ConfigDict()


class LiquidityReserveRequirementIngestionRequest(BaseModel):
    liquidity_reserve_requirements: list[LiquidityReserveRequirementRecord] = Field(
        ...,
        description="Effective-dated liquidity reserve requirements to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_requirement_uniqueness(self) -> "LiquidityReserveRequirementIngestionRequest":
        keys = [
            (
                requirement.client_id,
                requirement.portfolio_id,
                requirement.reserve_requirement_id,
                requirement.effective_from,
                requirement.requirement_version,
            )
            for requirement in self.liquidity_reserve_requirements
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("liquidity_reserve_requirements contains duplicate effective records")
        return self

    model_config = ConfigDict()
