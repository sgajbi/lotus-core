"""API contracts for governed risk-free series windows."""

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field

from .common import IntegrationWindow


class RiskFreeSeriesRequest(BaseModel):
    """Request a daily canonical risk-free series window."""

    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    window: IntegrationWindow = Field(..., description="Date window for series extraction.")
    frequency: Literal["daily"] = Field(
        ...,
        description="Requested output frequency label. Currently only daily is supported.",
        examples=["daily"],
    )
    currency: str = Field(..., description="Series currency.", examples=["USD"])
    series_mode: Literal["annualized_rate_series", "return_series"] = Field(
        ...,
        description="Risk-free series mode requested by the integration client.",
        examples=["annualized_rate_series"],
    )

    model_config = ConfigDict()


class RiskFreeSeriesPoint(BaseModel):
    """One canonical risk-free series point."""

    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    value: Decimal = Field(..., description="Risk-free series value.", examples=["0.0350000000"])
    value_convention: str = Field(
        ..., description="Value convention label.", examples=["annualized_rate"]
    )
    day_count_convention: str | None = Field(
        None, description="Day-count convention for annualized rates.", examples=["act_360"]
    )
    compounding_convention: str | None = Field(
        None, description="Compounding convention for rates.", examples=["simple"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])


class RiskFreeSeriesResponse(SourceDataProductRuntimeMetadata):
    """Canonical risk-free observations with deterministic source proof."""

    product_name: Literal["RiskFreeSeriesWindow"] = product_name_field("RiskFreeSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    currency: str = Field(..., description="Series currency code.", examples=["USD"])
    series_mode: Literal["annualized_rate_series", "return_series"]
    resolved_window: IntegrationWindow
    frequency: str
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw risk-free series scope.",
    )
    record_count: int = Field(..., ge=0)
    completeness_status: Literal["COMPLETE", "PARTIAL", "EMPTY"]
    points: list[RiskFreeSeriesPoint] = Field(default_factory=list)
    lineage: dict[str, str] = Field(
        default_factory=dict,
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )
