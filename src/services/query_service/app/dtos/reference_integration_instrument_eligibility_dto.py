from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


def _normalize_instrument_eligibility_security_ids(security_ids: list[str]) -> list[str]:
    normalized = [security_id.strip() for security_id in security_ids]
    if any(not security_id for security_id in normalized):
        raise ValueError("security_ids must contain non-empty identifiers")
    if len(normalized) != len(set(normalized)):
        raise ValueError("security_ids must not contain duplicates")
    return normalized


class InstrumentEligibilityBulkRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve effective eligibility profiles.",
        examples=["2026-04-10"],
    )
    security_ids: list[str] = Field(
        ...,
        description=(
            "Canonical security identifiers to resolve in one deterministic batch. Request order "
            "is preserved and unknown securities are returned explicitly."
        ),
        min_length=1,
        examples=[["AAPL", "MSFT", "PRIVCREDIT-A"]],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )
    include_restricted_rationale: bool = Field(
        False,
        description=(
            "Reserved operator/audit flag. The public DPM source product returns bounded "
            "restriction_reason_codes and never exposes sensitive free-text rationale."
        ),
        examples=[False],
    )

    @model_validator(mode="after")
    def validate_security_ids(self) -> "InstrumentEligibilityBulkRequest":
        self.security_ids = _normalize_instrument_eligibility_security_ids(self.security_ids)
        return self

    model_config = ConfigDict()


class InstrumentEligibilityRecord(BaseModel):
    security_id: str = Field(..., description="Canonical security identifier.", examples=["AAPL"])
    found: bool = Field(
        ...,
        description="Whether an effective eligibility profile was found for this security.",
        examples=[True],
    )
    eligibility_status: Literal["APPROVED", "RESTRICTED", "SELL_ONLY", "BANNED", "UNKNOWN"] = Field(
        ..., description="DPM eligibility status.", examples=["APPROVED"]
    )
    product_shelf_status: str = Field(
        ..., description="Product shelf status used by DPM execution.", examples=["APPROVED"]
    )
    buy_allowed: bool = Field(..., description="Whether DPM may buy this instrument.")
    sell_allowed: bool = Field(..., description="Whether DPM may sell this instrument.")
    restriction_reason_codes: list[str] = Field(
        default_factory=list,
        description="Bounded restriction codes suitable for downstream audit and explainability.",
        examples=[["PRIVATE_ASSET_REVIEW"]],
    )
    settlement_days: int | None = Field(
        None,
        description="Expected settlement cycle in business days; null when unknown.",
        examples=[2],
    )
    settlement_calendar_id: str | None = Field(
        None,
        description="Settlement calendar identifier; null when unknown.",
        examples=["US_NYSE"],
    )
    liquidity_tier: str | None = Field(None, description="Liquidity tier.", examples=["L1"])
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
    effective_from: date | None = Field(
        None, description="Resolved effective start date; null when unknown."
    )
    effective_to: date | None = Field(
        None, description="Resolved effective end date; null when open-ended or unknown."
    )
    quality_status: str = Field(
        ..., description="Source data quality status.", examples=["ACCEPTED"]
    )
    source_record_id: str | None = Field(
        None, description="Source record identifier for audit and replay."
    )

    model_config = ConfigDict()


class InstrumentEligibilitySupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for using this eligibility batch in DPM.",
        examples=["READY"],
    )
    reason: str = Field(
        ..., description="Bounded reason code for eligibility readiness.", examples=["READY"]
    )
    requested_count: int = Field(..., description="Number of requested security identifiers.")
    resolved_count: int = Field(..., description="Number with effective eligibility profiles.")
    missing_security_ids: list[str] = Field(
        default_factory=list,
        description="Security identifiers with no effective eligibility profile.",
        examples=[["UNKNOWN_SEC"]],
    )

    model_config = ConfigDict()


class InstrumentEligibilityBulkResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["InstrumentEligibilityProfile"] = product_name_field(
        "InstrumentEligibilityProfile"
    )
    product_version: Literal["v1"] = product_version_field()
    records: list[InstrumentEligibilityRecord] = Field(
        ...,
        description="Eligibility records in the same order as request security_ids.",
    )
    supportability: InstrumentEligibilitySupportability = Field(
        ..., description="Batch-level DPM source-data readiness."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Core source lineage metadata for audit and diagnostics.",
    )

    model_config = ConfigDict()
