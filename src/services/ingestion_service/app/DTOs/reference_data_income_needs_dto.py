from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClientIncomeNeedsScheduleRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the income-needs schedule.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the schedule.")
    mandate_id: str | None = Field(None, description="Mandate identifier when schedule-specific.")
    schedule_id: str = Field(..., description="Source-owned income-needs schedule identifier.")
    need_type: Literal[
        "RECURRING_WITHDRAWAL", "LIVING_EXPENSE", "COMMITTED_OUTFLOW", "INCOME_NEED", "OTHER"
    ] = Field(..., description="Bounded income need type.")
    need_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Income-needs lifecycle status."
    )
    amount: Decimal = Field(
        ..., gt=Decimal(0), description="Source-supplied amount for the income need."
    )
    currency: str = Field(
        ...,
        description=(
            "Canonical three-letter currency for the income-needs amount used by cashflow, "
            "liquidity, and funding calculations."
        ),
    )
    frequency: Literal["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"] = Field(
        ..., description="Source-supplied income-needs frequency."
    )
    start_date: date = Field(..., description="Income-needs schedule start date.")
    end_date: date | None = Field(None, description="Income-needs schedule end date.")
    priority: int = Field(1, ge=1)
    funding_policy: str | None = Field(None)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    @model_validator(mode="after")
    def validate_schedule(self) -> "ClientIncomeNeedsScheduleRecord":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    model_config = ConfigDict()


class ClientIncomeNeedsScheduleIngestionRequest(BaseModel):
    income_needs_schedules: list[ClientIncomeNeedsScheduleRecord] = Field(
        ...,
        description="Effective-dated client income-needs schedules to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_schedule_uniqueness(self) -> "ClientIncomeNeedsScheduleIngestionRequest":
        keys = [
            (
                schedule.client_id,
                schedule.portfolio_id,
                schedule.schedule_id,
                schedule.start_date,
            )
            for schedule in self.income_needs_schedules
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("income_needs_schedules contains duplicate effective records")
        return self

    model_config = ConfigDict()
