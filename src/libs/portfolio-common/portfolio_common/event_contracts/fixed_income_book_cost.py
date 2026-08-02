"""Strict transport contract for fixed-income book-cost source authority."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.eventing import portfolio_security_lot_partition_key
from portfolio_common.pydantic_financial_numeric import (
    ExactDecimal18_10,
    ExactNonNegativeDecimal18_10,
    ExactPositiveDecimal18_10,
)

FIXED_INCOME_BOOK_COST_AUTHORITY_EVENT_TYPE = "fixed_income.book_cost.authority.received"
FIXED_INCOME_BOOK_COST_AUTHORITY_SCHEMA_VERSION = "1.0.0"

_STRICT_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    allow_inf_nan=False,
)

_PositiveStrictVersion = Annotated[int, Field(strict=True, ge=1)]
_ExactPeriodRate = Annotated[ExactDecimal18_10, Field(gt=Decimal(-1))]


class FixedIncomeBookCostAuthorityStatus(StrEnum):
    """Source lifecycle state shared by assignment and fact authority."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class FixedIncomeDiscountOrigin(StrEnum):
    """Source-owned economic origin of a premium or discount."""

    AT_PAR = "AT_PAR"
    PURCHASE_PREMIUM = "PURCHASE_PREMIUM"
    MARKET_DISCOUNT = "MARKET_DISCOUNT"
    ORIGINAL_ISSUE_DISCOUNT = "ORIGINAL_ISSUE_DISCOUNT"


class FixedIncomeYieldApplication(StrEnum):
    """Explicit interpretation of an authoritative yield or period rate."""

    ANNUAL_EFFECTIVE = "ANNUAL_EFFECTIVE"
    ANNUAL_NOMINAL_SIMPLE = "ANNUAL_NOMINAL_SIMPLE"
    PER_PERIOD_EFFECTIVE = "PER_PERIOD_EFFECTIVE"


class FixedIncomeBookCostAuthorityScope(BaseModel):
    """Exact tenant and source-lot scope whose corrections remain ordered."""

    tenant_id: str = Field(min_length=1, max_length=160)
    legal_book_id: str = Field(min_length=1, max_length=160)
    portfolio_id: str = Field(min_length=1, max_length=160)
    security_id: str = Field(min_length=1, max_length=160)
    lot_id: str = Field(min_length=1, max_length=160)

    def partition_key(self) -> str:
        """Return the domain-owned event key for this source-lot authority stream."""

        return cast(
            str,
            portfolio_security_lot_partition_key(
                self.portfolio_id,
                self.security_id,
                self.lot_id,
                tenant_id=self.tenant_id,
                legal_book_id=self.legal_book_id,
            ).value,
        )

    model_config = _STRICT_MODEL_CONFIG


class FixedIncomeBookCostAuthoritySource(BaseModel):
    """Immutable upstream correction identity and observation evidence."""

    source_system: str = Field(min_length=1, max_length=160)
    source_record_id: str = Field(min_length=1, max_length=200)
    source_revision: str = Field(min_length=1, max_length=200)
    source_version: _PositiveStrictVersion
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_aware_observation(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset")
        return value.astimezone(UTC)

    model_config = _STRICT_MODEL_CONFIG


class FixedIncomeBookCostAuthorityHeader(BaseModel):
    """Fields common to every effective-dated authority family."""

    scope: FixedIncomeBookCostAuthorityScope
    source: FixedIncomeBookCostAuthoritySource
    status: FixedIncomeBookCostAuthorityStatus
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def validate_effective_window(self) -> FixedIncomeBookCostAuthorityHeader:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        return self

    model_config = _STRICT_MODEL_CONFIG


class PolicyAssignmentAuthorityContract(BaseModel):
    """Assign one exact source lot to one supported amortized-cost policy."""

    authority_type: Literal["POLICY_ASSIGNMENT"] = "POLICY_ASSIGNMENT"
    header: FixedIncomeBookCostAuthorityHeader
    policy_id: str = Field(min_length=1, max_length=160)
    policy_version: _PositiveStrictVersion
    assignment_reason: str = Field(min_length=1, max_length=500)

    model_config = _STRICT_MODEL_CONFIG


class CleanCostBasisAuthorityContract(BaseModel):
    """Authoritative clean acquisition cost and contractual redemption value."""

    authority_type: Literal["CLEAN_COST_BASIS"] = "CLEAN_COST_BASIS"
    header: FixedIncomeBookCostAuthorityHeader
    currency: str = Field(min_length=3, max_length=3)
    initial_clean_cost_local: ExactNonNegativeDecimal18_10
    fees_in_basis_local: ExactNonNegativeDecimal18_10
    redemption_value_local: ExactNonNegativeDecimal18_10
    discount_origin: FixedIncomeDiscountOrigin

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return cast(str, normalize_currency_code(value))

    @model_validator(mode="after")
    def validate_discount_origin(self) -> CleanCostBasisAuthorityContract:
        opening = self.initial_clean_cost_local
        redemption = self.redemption_value_local
        if opening > redemption:
            expected = FixedIncomeDiscountOrigin.PURCHASE_PREMIUM
            if self.discount_origin is not expected:
                raise ValueError("premium basis requires PURCHASE_PREMIUM classification")
        elif opening == redemption:
            if self.discount_origin is not FixedIncomeDiscountOrigin.AT_PAR:
                raise ValueError("par basis requires AT_PAR classification")
        elif self.discount_origin not in {
            FixedIncomeDiscountOrigin.MARKET_DISCOUNT,
            FixedIncomeDiscountOrigin.ORIGINAL_ISSUE_DISCOUNT,
        }:
            raise ValueError("discount basis requires MARKET_DISCOUNT or ORIGINAL_ISSUE_DISCOUNT")
        return self

    model_config = _STRICT_MODEL_CONFIG


class AmortizationPeriodContract(BaseModel):
    """One authoritative contractual period and its supplied economics."""

    period_start_date: date
    period_end_date: date
    year_fraction: ExactPositiveDecimal18_10
    cash_coupon_local: ExactNonNegativeDecimal18_10
    supplied_period_rate: _ExactPeriodRate | None = None

    @model_validator(mode="after")
    def validate_period(self) -> AmortizationPeriodContract:
        if self.period_end_date <= self.period_start_date:
            raise ValueError("period_end_date must be after period_start_date")
        return self

    model_config = _STRICT_MODEL_CONFIG


class AmortizationScheduleAuthorityContract(BaseModel):
    """Authoritative contractual schedule for one source lot."""

    authority_type: Literal["AMORTIZATION_SCHEDULE"] = "AMORTIZATION_SCHEDULE"
    header: FixedIncomeBookCostAuthorityHeader
    schedule_version: _PositiveStrictVersion
    year_fraction_method_id: str = Field(min_length=1, max_length=160)
    year_fraction_method_version: _PositiveStrictVersion
    periods: tuple[AmortizationPeriodContract, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_contiguous_periods(self) -> AmortizationScheduleAuthorityContract:
        for previous, current in zip(self.periods, self.periods[1:]):
            if previous.period_end_date != current.period_start_date:
                raise ValueError("periods must be contiguous and ordered")
        return self

    model_config = _STRICT_MODEL_CONFIG


class EffectiveYieldAuthorityContract(BaseModel):
    """Authoritative annual yield and its explicit interpretation."""

    authority_type: Literal["EFFECTIVE_YIELD"] = "EFFECTIVE_YIELD"
    header: FixedIncomeBookCostAuthorityHeader
    annual_yield: ExactDecimal18_10
    yield_application: FixedIncomeYieldApplication

    @model_validator(mode="after")
    def reject_period_rate_as_annual_authority(self) -> EffectiveYieldAuthorityContract:
        if self.yield_application is FixedIncomeYieldApplication.PER_PERIOD_EFFECTIVE:
            raise ValueError("per-period rates belong to the amortization schedule")
        if (
            self.yield_application is FixedIncomeYieldApplication.ANNUAL_EFFECTIVE
            and self.annual_yield <= Decimal(-1)
        ):
            raise ValueError("annual effective yield must be greater than negative one")
        return self

    model_config = _STRICT_MODEL_CONFIG


FixedIncomeBookCostAuthority = Annotated[
    PolicyAssignmentAuthorityContract
    | CleanCostBasisAuthorityContract
    | AmortizationScheduleAuthorityContract
    | EffectiveYieldAuthorityContract,
    Field(discriminator="authority_type"),
]


class FixedIncomeBookCostAuthorityEvent(BaseModel):
    """Versioned event envelope accepted by the transaction-processing owner."""

    event_type: Literal["fixed_income.book_cost.authority.received"] = (
        "fixed_income.book_cost.authority.received"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    authority: FixedIncomeBookCostAuthority

    @property
    def partition_key(self) -> str:
        """Return the exact source-lot ordering key for broker publication."""

        return self.authority.header.scope.partition_key()

    def content_hash(self) -> str:
        """Bind the complete normalized transport contract for idempotency and audit."""

        return cast(str, canonical_content_hash(self.model_dump(mode="json")))

    model_config = _STRICT_MODEL_CONFIG
