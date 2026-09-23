from datetime import date

from portfolio_common.domain.business_calendar import normalize_business_calendar_code
from pydantic import BaseModel, Field, field_validator


class BusinessDate(BaseModel):
    business_date: date = Field(
        ...,
        description="Canonical business date to open for processing.",
        examples=["2026-03-10"],
    )
    calendar_code: str = Field(
        default="GLOBAL",
        description="Business calendar identifier (for example: GLOBAL, SIX_CH, NYSE_US).",
        examples=["GLOBAL"],
    )
    market_code: str | None = Field(
        default=None,
        description="Optional market or venue code associated with the business date.",
        examples=["XSWX"],
    )
    source_system: str | None = Field(
        default=None,
        description="Optional upstream source system identifier for lineage.",
        examples=["lotus-manage"],
    )
    source_batch_id: str | None = Field(
        default=None,
        description="Optional upstream batch identifier for lineage and replay tracking.",
        examples=["business-dates-20260310-am"],
    )

    @field_validator("calendar_code", mode="before")
    @classmethod
    def _normalize_calendar_code(cls, value: object) -> str:
        return normalize_business_calendar_code(value)


class BusinessDateIngestionRequest(BaseModel):
    business_dates: list[BusinessDate] = Field(
        ...,
        description=(
            "Business dates to register for downstream valuation and timeseries scheduling."
        ),
        examples=[
            [
                {
                    "business_date": "2026-03-10",
                    "calendar_code": "GLOBAL",
                    "market_code": "XSWX",
                    "source_system": "lotus-manage",
                    "source_batch_id": "business-dates-20260310-am",
                }
            ]
        ],
    )
