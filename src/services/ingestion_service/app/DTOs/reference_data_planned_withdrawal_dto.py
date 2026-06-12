from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PlannedWithdrawalScheduleRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the withdrawal schedule.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the withdrawal schedule.")
    mandate_id: str | None = Field(None, description="Mandate identifier when withdrawal-specific.")
    withdrawal_schedule_id: str = Field(..., description="Source-owned withdrawal schedule id.")
    withdrawal_type: Literal["PLANNED_WITHDRAWAL", "INCOME_DISTRIBUTION", "OTHER"] = Field(
        ..., description="Bounded planned withdrawal type."
    )
    withdrawal_status: Literal["active", "inactive", "suspended", "cancelled"] = Field(
        "active", description="Withdrawal lifecycle status."
    )
    amount: Decimal = Field(
        ..., gt=Decimal(0), description="Source-supplied planned withdrawal amount."
    )
    currency: str = Field(
        ...,
        description=(
            "Canonical three-letter currency for the planned withdrawal amount used by "
            "cashflow and liquidity planning calculations."
        ),
    )
    scheduled_date: date = Field(..., description="Scheduled withdrawal date.")
    recurrence_frequency: (
        Literal["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"] | None
    ) = Field(None)
    purpose_code: str | None = Field(None)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class PlannedWithdrawalScheduleIngestionRequest(BaseModel):
    planned_withdrawal_schedules: list[PlannedWithdrawalScheduleRecord] = Field(
        ...,
        description="Planned withdrawal schedules to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_withdrawal_uniqueness(self) -> "PlannedWithdrawalScheduleIngestionRequest":
        keys = [
            (
                withdrawal.client_id,
                withdrawal.portfolio_id,
                withdrawal.withdrawal_schedule_id,
                withdrawal.scheduled_date,
            )
            for withdrawal in self.planned_withdrawal_schedules
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("planned_withdrawal_schedules contains duplicate effective records")
        return self

    model_config = ConfigDict()
