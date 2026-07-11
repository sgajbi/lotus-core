"""API contracts for client income, reserve, and withdrawal source evidence."""

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class ClientIncomeNeedsScheduleRequest(BaseModel):
    """Select effective client income-needs schedules for one portfolio."""

    as_of_date: date = Field(
        ...,
        description="Business date used to resolve active client income-needs schedules.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    include_inactive_schedules: bool = Field(
        False, description="When false, excludes inactive income-needs schedules."
    )
    model_config = ConfigDict()


class ClientIncomeNeedsScheduleEntry(BaseModel):
    """One effective client income-needs schedule."""

    schedule_id: str = Field(..., description="Source-owned income-needs schedule identifier.")
    need_type: str = Field(..., description="Bounded income need type.")
    need_status: str = Field(..., description="Income-needs lifecycle status.")
    amount: Decimal = Field(..., description="Source-supplied income need amount.")
    currency: str = Field(..., description="Currency for amount.")
    frequency: str = Field(..., description="Income-needs cadence.")
    start_date: date = Field(..., description="Income-needs schedule start date.")
    end_date: date | None = Field(None, description="Income-needs schedule end date.")
    priority: int = Field(..., description="Source-supplied priority.")
    funding_policy: str | None = Field(None, description="Bank/source funding policy reference.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")
    model_config = ConfigDict()


class ClientIncomeNeedsScheduleSupportability(BaseModel):
    """Operational readiness of resolved income-needs evidence."""

    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using income-needs schedules as DPM evidence."
    )
    reason: str = Field(..., description="Machine-readable supportability reason.")
    schedule_count: int = Field(..., ge=0, description="Number of effective schedules returned.")
    missing_data_families: list[str] = Field(default_factory=list)
    model_config = ConfigDict()


class ClientIncomeNeedsScheduleResponse(SourceDataProductRuntimeMetadata):
    """Effective income-needs schedules with lineage and supportability."""

    product_name: Literal["ClientIncomeNeedsSchedule"] = product_name_field(
        "ClientIncomeNeedsSchedule"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the schedules.")
    client_id: str = Field(..., description="Client identifier bound to the schedules.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for schedule resolution.")
    schedules: list[ClientIncomeNeedsScheduleEntry] = Field(
        default_factory=list,
        description="Deterministically ordered effective client income-needs schedules.",
    )
    supportability: ClientIncomeNeedsScheduleSupportability
    lineage: dict[str, str] = Field(default_factory=dict)
    model_config = ConfigDict()


class LiquidityReserveRequirementRequest(BaseModel):
    """Select effective liquidity reserve requirements for one portfolio."""

    as_of_date: date = Field(
        ...,
        description="Business date used to resolve active liquidity reserve requirements.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    include_inactive_requirements: bool = Field(
        False, description="When false, excludes inactive liquidity reserve requirements."
    )
    model_config = ConfigDict()


class LiquidityReserveRequirementEntry(BaseModel):
    """One effective liquidity reserve requirement."""

    reserve_requirement_id: str = Field(..., description="Source-owned reserve requirement id.")
    reserve_type: str = Field(..., description="Bounded reserve requirement type.")
    reserve_status: str = Field(..., description="Reserve requirement lifecycle status.")
    required_amount: Decimal = Field(..., description="Required reserve amount.")
    currency: str = Field(..., description="Currency for required_amount.")
    horizon_days: int = Field(..., description="Reserve horizon in calendar days.")
    priority: int = Field(..., description="Source-supplied priority.")
    policy_source: str = Field(..., description="Source policy or bank reference.")
    effective_from: date = Field(..., description="Requirement effective start date.")
    effective_to: date | None = Field(None, description="Requirement effective end date.")
    requirement_version: int = Field(..., description="Selected requirement version.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")
    model_config = ConfigDict()


class LiquidityReserveRequirementSupportability(BaseModel):
    """Operational readiness of resolved reserve evidence."""

    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using reserve requirements as DPM evidence."
    )
    reason: str = Field(..., description="Machine-readable supportability reason.")
    requirement_count: int = Field(
        ..., ge=0, description="Number of effective reserve requirements returned."
    )
    missing_data_families: list[str] = Field(default_factory=list)
    model_config = ConfigDict()


class LiquidityReserveRequirementResponse(SourceDataProductRuntimeMetadata):
    """Effective reserve requirements with lineage and supportability."""

    product_name: Literal["LiquidityReserveRequirement"] = product_name_field(
        "LiquidityReserveRequirement"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the requirements.")
    client_id: str = Field(..., description="Client identifier bound to the requirements.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for requirement resolution.")
    requirements: list[LiquidityReserveRequirementEntry] = Field(
        default_factory=list,
        description="Deterministically ordered effective liquidity reserve requirements.",
    )
    supportability: LiquidityReserveRequirementSupportability
    lineage: dict[str, str] = Field(default_factory=dict)
    model_config = ConfigDict()


class PlannedWithdrawalScheduleRequest(BaseModel):
    """Select planned withdrawals in a bounded forward horizon."""

    as_of_date: date = Field(
        ...,
        description="Business date used as the lower bound for planned withdrawal schedules.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    horizon_days: int = Field(365, ge=1, le=3660, description="Forward withdrawal horizon.")
    include_inactive_withdrawals: bool = Field(
        False, description="When false, excludes inactive planned withdrawal schedules."
    )
    model_config = ConfigDict()


class PlannedWithdrawalScheduleEntry(BaseModel):
    """One planned withdrawal source record."""

    withdrawal_schedule_id: str = Field(..., description="Source-owned withdrawal schedule id.")
    withdrawal_type: str = Field(..., description="Bounded planned withdrawal type.")
    withdrawal_status: str = Field(..., description="Withdrawal lifecycle status.")
    amount: Decimal = Field(..., description="Source-supplied planned withdrawal amount.")
    currency: str = Field(..., description="Currency for amount.")
    scheduled_date: date = Field(..., description="Scheduled withdrawal date.")
    recurrence_frequency: str | None = Field(None, description="Optional recurrence cadence.")
    purpose_code: str | None = Field(None, description="Optional source purpose code.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")
    model_config = ConfigDict()


class PlannedWithdrawalScheduleSupportability(BaseModel):
    """Operational readiness of resolved withdrawal evidence."""

    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using planned withdrawals as DPM evidence."
    )
    reason: str = Field(..., description="Machine-readable supportability reason.")
    withdrawal_count: int = Field(..., ge=0, description="Number of withdrawals returned.")
    missing_data_families: list[str] = Field(default_factory=list)
    model_config = ConfigDict()


class PlannedWithdrawalScheduleResponse(SourceDataProductRuntimeMetadata):
    """Planned withdrawals with lineage and supportability."""

    product_name: Literal["PlannedWithdrawalSchedule"] = product_name_field(
        "PlannedWithdrawalSchedule"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the schedules.")
    client_id: str = Field(..., description="Client identifier bound to the schedules.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for schedule resolution.")
    horizon_days: int = Field(..., description="Forward withdrawal horizon.")
    withdrawals: list[PlannedWithdrawalScheduleEntry] = Field(
        default_factory=list,
        description="Deterministically ordered planned withdrawals in the requested horizon.",
    )
    supportability: PlannedWithdrawalScheduleSupportability
    lineage: dict[str, str] = Field(default_factory=dict)
    model_config = ConfigDict()
