from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_BUY_BLOCKING_SHELF_STATUSES = {"BANNED", "SUSPENDED"}


def _validate_effective_window(effective_from: date, effective_to: date | None) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("effective_to must be on or after effective_from")


def _validate_buy_permission(product_shelf_status: str, buy_allowed: bool) -> None:
    if product_shelf_status in _BUY_BLOCKING_SHELF_STATUSES and buy_allowed:
        raise ValueError("buy_allowed must be false for banned or suspended instruments")


def _validate_sell_permission(product_shelf_status: str, sell_allowed: bool) -> None:
    if product_shelf_status == "BANNED" and sell_allowed:
        raise ValueError("sell_allowed must be false for banned instruments")


class InstrumentEligibilityProfileRecord(BaseModel):
    security_id: str = Field(
        ..., description="Canonical instrument/security identifier.", examples=["AAPL"]
    )
    eligibility_status: Literal["APPROVED", "RESTRICTED", "SELL_ONLY", "BANNED", "UNKNOWN"] = Field(
        ..., description="DPM eligibility status for this instrument.", examples=["APPROVED"]
    )
    product_shelf_status: Literal["APPROVED", "RESTRICTED", "SELL_ONLY", "BANNED", "SUSPENDED"] = (
        Field(..., description="Product shelf status used by DPM execution.", examples=["APPROVED"])
    )
    buy_allowed: bool = Field(
        ..., description="Whether DPM may create buy orders for this instrument.", examples=[True]
    )
    sell_allowed: bool = Field(
        ..., description="Whether DPM may create sell orders for this instrument.", examples=[True]
    )
    restriction_reason_codes: list[str] = Field(
        default_factory=list,
        description=(
            "Bounded restriction codes. Sensitive free-text rationale is not returned by the "
            "DPM API."
        ),
        examples=[["PRIVATE_ASSET_REVIEW"]],
    )
    restriction_rationale: str | None = Field(
        None,
        description="Operator-only source rationale retained for audit; not exposed downstream.",
        examples=["Investment office review required before new buys."],
    )
    settlement_days: int = Field(
        ..., description="Expected settlement cycle in business days.", ge=0, examples=[2]
    )
    settlement_calendar_id: str = Field(
        ..., description="Settlement calendar identifier.", examples=["US_NYSE"]
    )
    liquidity_tier: Literal["L1", "L2", "L3", "L4", "L5"] | None = Field(
        None, description="Liquidity tier used by DPM controls.", examples=["L1"]
    )
    issuer_id: str | None = Field(None, description="Direct issuer identifier.", examples=["APPLE"])
    issuer_name: str | None = Field(
        None, description="Direct issuer name.", examples=["Apple Inc."]
    )
    ultimate_parent_issuer_id: str | None = Field(
        None, description="Ultimate parent issuer identifier.", examples=["APPLE_PARENT"]
    )
    ultimate_parent_issuer_name: str | None = Field(
        None, description="Ultimate parent issuer name.", examples=["Apple Inc."]
    )
    asset_class: str | None = Field(None, description="Asset class label.", examples=["Equity"])
    country_of_risk: str | None = Field(None, description="Country of risk.", examples=["US"])
    effective_from: date = Field(
        ..., description="Eligibility effective start date.", examples=["2026-04-01"]
    )
    effective_to: date | None = Field(
        None, description="Eligibility effective end date, null when open-ended.", examples=None
    )
    eligibility_version: int = Field(
        1, description="Eligibility version used for effective-date tie-breaks.", ge=1
    )
    source_system: str | None = Field(
        None, description="Upstream shelf/compliance source system.", examples=["product_shelf"]
    )
    source_record_id: str | None = Field(
        None, description="Source record identifier for replay.", examples=["AAPL-elig-20260401"]
    )
    observed_at: datetime | None = Field(
        None, description="Timestamp when the source observed or published this profile."
    )
    quality_status: str = Field(
        "accepted",
        description="Data quality status for the eligibility profile.",
        examples=["accepted"],
    )

    @model_validator(mode="after")
    def validate_effective_window(self) -> "InstrumentEligibilityProfileRecord":
        _validate_effective_window(self.effective_from, self.effective_to)
        _validate_buy_permission(self.product_shelf_status, self.buy_allowed)
        _validate_sell_permission(self.product_shelf_status, self.sell_allowed)
        return self

    model_config = ConfigDict()


class InstrumentEligibilityProfileIngestionRequest(BaseModel):
    eligibility_profiles: list[InstrumentEligibilityProfileRecord] = Field(
        ...,
        description="Effective-dated instrument eligibility profiles to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_profile_uniqueness(self) -> "InstrumentEligibilityProfileIngestionRequest":
        keys = [
            (profile.security_id, profile.effective_from, profile.eligibility_version)
            for profile in self.eligibility_profiles
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("eligibility_profiles contains duplicate effective records")
        return self

    model_config = ConfigDict()
