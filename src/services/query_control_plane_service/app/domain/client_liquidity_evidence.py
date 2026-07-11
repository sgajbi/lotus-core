"""Domain records for client income, reserve, and withdrawal evidence."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ClientIncomeNeedSourceRecord:
    """Persistence-independent client income-needs evidence."""

    schedule_id: str
    need_type: str
    need_status: str
    amount: Decimal
    currency: str
    frequency: str
    start_date: date
    end_date: date | None
    priority: int
    funding_policy: str | None
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class LiquidityReserveRequirementSourceRecord:
    """Persistence-independent liquidity reserve evidence."""

    reserve_requirement_id: str
    reserve_type: str
    reserve_status: str
    required_amount: Decimal
    currency: str
    horizon_days: int
    priority: int
    policy_source: str
    effective_from: date
    effective_to: date | None
    requirement_version: int
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class PlannedWithdrawalSourceRecord:
    """Persistence-independent planned withdrawal evidence."""

    withdrawal_schedule_id: str
    withdrawal_type: str
    withdrawal_status: str
    amount: Decimal
    currency: str
    scheduled_date: date
    recurrence_frequency: str | None
    purpose_code: str | None
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
