from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReportingCurrencySupportStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNAVAILABLE = "UNAVAILABLE"


class ReportingCurrencyFxEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_currency: str = Field(..., min_length=3, max_length=3, examples=["EUR"])
    rate_date: date | None = Field(
        default=None,
        description="Source-owned FX observation date, which must equal the requested as-of date.",
    )
    rate_available: bool = Field(
        ..., description="Whether an authoritative FX rate is available for this source currency."
    )


class ReportingCurrencySupportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: str = Field(
        default="ReportingCurrencySupport:v1",
        description="Stable source-owned contract identifier.",
    )
    operation: str = Field(
        default="performance-restatement",
        description="Operation for which supportability was evaluated.",
    )
    scope: str = Field(
        default="portfolio-as-of",
        description="Support is evaluated for one portfolio and an effective as-of date.",
    )
    portfolio_id: str
    tenant_id: str | None = None
    reporting_currency: str = Field(..., min_length=3, max_length=3)
    as_of_date: date
    status: ReportingCurrencySupportStatus
    supported: bool = Field(
        ..., description="True only when every source currency has required FX evidence."
    )
    reason_code: str = Field(..., description="Machine-readable supportability outcome.")
    source_currencies: list[str] = Field(
        default_factory=list,
        description="Currencies observed in the portfolio source state at or before as-of date.",
    )
    missing_source_currencies: list[str] = Field(
        default_factory=list,
        description="Observed source currencies without an authoritative FX rate.",
    )
    fx_evidence: list[ReportingCurrencyFxEvidence] = Field(default_factory=list)
    observed_selector_currency: bool | None = Field(
        default=None,
        description=(
            "Whether the requested code appears in Core's selector catalog. This is an observed "
            "selector fact only and never implies restatement support."
        ),
    )
