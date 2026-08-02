"""Public supportability contract for lot-level amortized book cost."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BookCostSourceReferenceResponse(BaseModel):
    source_system: str
    source_record_id: str
    source_revision: str
    source_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime

    model_config = ConfigDict(extra="forbid")


class BookCostCalculationLineageResponse(BaseModel):
    algorithm_id: str
    algorithm_version: int = Field(ge=1)
    intermediate_precision: int = Field(ge=1)
    input_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    calculation_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    numeric_output_policy: dict[str, object] | None = None

    model_config = ConfigDict(extra="forbid")


class BookCostPeriodRecognitionResponse(BaseModel):
    period_ordinal: int = Field(ge=1)
    period_start_date: date
    period_end_date: date
    year_fraction: Decimal
    period_rate: Decimal | None
    begin_amortized_cost_local: Decimal
    interest_income_local: Decimal
    cash_coupon_local: Decimal
    amortization_amount_local: Decimal
    end_amortized_cost_local: Decimal
    rounding_adjustment_local: Decimal
    calculation_output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    period_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid")


class FixedIncomeBookCostAsOfResponse(BaseModel):
    tenant_id: str
    legal_book_id: str
    portfolio_id: str
    security_id: str
    lot_id: str
    requested_as_of_date: date
    profile_id: str
    profile_version: int = Field(ge=1)
    profile_effective_date: date
    status: str
    eligibility_reason: str | None
    policy_id: str | None
    policy_version: int | None
    schedule_version: int | None
    currency: str | None
    direction: str | None
    book_cost_local_as_of: Decimal | None
    recognized_through_date: date | None
    next_recognition_date: date | None
    recognized_period_count: int = Field(ge=0)
    total_period_count: int = Field(ge=0)
    initial_amortized_cost_local: Decimal | None
    redemption_value_local: Decimal | None
    final_amortized_cost_local: Decimal | None
    residual_local: Decimal | None
    authority_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    profile_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_references: list[BookCostSourceReferenceResponse]
    calculation_lineage: BookCostCalculationLineageResponse | None
    latest_recognized_period: BookCostPeriodRecognitionResponse | None

    model_config = ConfigDict(extra="forbid")
