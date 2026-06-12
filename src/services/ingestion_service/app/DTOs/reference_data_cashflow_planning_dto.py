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
