from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskFreeSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["rf_usd_3m"])
    risk_free_curve_id: str = Field(
        ..., description="Risk-free curve identifier.", examples=["USD_SOFR_3M"]
    )
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    value: Decimal = Field(..., description="Risk-free value.", examples=["0.0350000000"])
    value_convention: Literal["annualized_rate", "period_return"] = Field(
        ...,
        description="Risk-free value convention.",
        examples=["annualized_rate"],
    )
    day_count_convention: str | None = Field(
        None,
        description="Day-count convention for annualized rates.",
        examples=["act_360"],
    )
    compounding_convention: str | None = Field(
        None,
        description="Compounding convention.",
        examples=["simple"],
    )
    series_currency: str = Field(
        ...,
        description="Canonical three-letter currency for the risk-free series.",
        examples=["USD"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the risk-free curve series record.",
        examples=["2026-01-02T06:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["BLOOMBERG"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["rf_20260102"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("series_currency", mode="before")
    @classmethod
    def _normalize_series_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class RiskFreeSeriesIngestionRequest(BaseModel):
    risk_free_series: list[RiskFreeSeriesRecord] = Field(
        ...,
        description="Risk-free series records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "series_id": "rf_usd_3m",
                    "risk_free_curve_id": "USD_SOFR_3M",
                    "series_date": "2026-01-02",
                    "value": "0.0350000000",
                    "value_convention": "annualized_rate",
                    "series_currency": "USD",
                }
            ]
        ],
    )

    model_config = ConfigDict()
