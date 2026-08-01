"""Source-versioned facts for lot-level amortized-cost calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    canonical_content_hash,
)
from portfolio_common.domain.currency import normalize_currency_code

from .authority import LotBookCostAuthorityScope
from .calculation import AmortizationPeriodInput
from .policy import YieldApplicationConvention


class AmortizedCostSourceFactStatus(StrEnum):
    """Lifecycle state of one source-owned amortized-cost input fact."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class DiscountOriginClassification(StrEnum):
    """Source-owned classification of the lot's premium or discount origin."""

    AT_PAR = "AT_PAR"
    PURCHASE_PREMIUM = "PURCHASE_PREMIUM"
    MARKET_DISCOUNT = "MARKET_DISCOUNT"
    ORIGINAL_ISSUE_DISCOUNT = "ORIGINAL_ISSUE_DISCOUNT"


@dataclass(frozen=True, slots=True)
class AmortizedCostSourceMetadata:
    """Immutable upstream correction identity shared by book-cost source facts."""

    source_system: str
    source_record_id: str
    source_revision: str
    fact_version: int
    observed_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("source_system", "source_record_id", "source_revision"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        _require_positive_integer(self.fact_version, "fact_version")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

    def lineage_payload(self) -> dict[str, object]:
        """Return normalized metadata for deterministic fact hashing."""

        return {
            "fact_version": self.fact_version,
            "observed_at": self.observed_at,
            "source_record_id": self.source_record_id,
            "source_revision": self.source_revision,
            "source_system": self.source_system,
        }


@dataclass(frozen=True, slots=True)
class LotAmortizedCostBasisFact:
    """Authoritative clean acquisition and redemption basis for one source lot."""

    scope: LotBookCostAuthorityScope
    currency: str
    initial_clean_cost_local: Decimal
    fees_in_basis_local: Decimal
    redemption_value_local: Decimal
    discount_origin: DiscountOriginClassification
    valid_from: date
    valid_to: date | None
    fact_status: AmortizedCostSourceFactStatus
    source: AmortizedCostSourceMetadata

    def __post_init__(self) -> None:
        _require_scope(self.scope)
        object.__setattr__(self, "currency", normalize_currency_code(self.currency))
        _require_nonnegative_finite(self.initial_clean_cost_local, "initial_clean_cost_local")
        _require_nonnegative_finite(self.fees_in_basis_local, "fees_in_basis_local")
        _require_nonnegative_finite(self.redemption_value_local, "redemption_value_local")
        if not isinstance(self.discount_origin, DiscountOriginClassification):
            raise TypeError("discount_origin must be a DiscountOriginClassification")
        _require_fact_window(self.valid_from, self.valid_to)
        _require_fact_status(self.fact_status)
        _require_source(self.source)
        self._validate_discount_origin()

    @property
    def source_record_key(self) -> tuple[str, str, str, str, str, str, str]:
        return (*self.scope.key, self.source.source_system, self.source.source_record_id)

    def is_effective_on(self, effective_date: date) -> bool:
        return _is_effective_on(self.valid_from, self.valid_to, effective_date)

    def content_hash(self) -> str:
        """Bind clean-cost economics and exact source authority."""

        return _fact_content_hash(
            fact_type="LOT_AMORTIZED_COST_BASIS",
            scope=self.scope,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            fact_status=self.fact_status,
            source=self.source,
            economics={
                "currency": self.currency,
                "discount_origin": self.discount_origin,
                "fees_in_basis_local": self.fees_in_basis_local,
                "initial_clean_cost_local": self.initial_clean_cost_local,
                "redemption_value_local": self.redemption_value_local,
            },
        )

    def source_reference(self) -> FinancialSourceReference:
        return _source_reference(self.source, self.content_hash())

    def _validate_discount_origin(self) -> None:
        opening = self.initial_clean_cost_local
        if opening > self.redemption_value_local:
            expected = DiscountOriginClassification.PURCHASE_PREMIUM
            if self.discount_origin is not expected:
                raise ValueError("premium basis requires PURCHASE_PREMIUM classification")
        elif opening == self.redemption_value_local:
            if self.discount_origin is not DiscountOriginClassification.AT_PAR:
                raise ValueError("par basis requires AT_PAR classification")
        elif self.discount_origin not in {
            DiscountOriginClassification.MARKET_DISCOUNT,
            DiscountOriginClassification.ORIGINAL_ISSUE_DISCOUNT,
        }:
            raise ValueError("discount basis requires MARKET_DISCOUNT or ORIGINAL_ISSUE_DISCOUNT")


@dataclass(frozen=True, slots=True)
class LotEffectiveYieldFact:
    """Authoritative annual yield and interpretation for one source lot."""

    scope: LotBookCostAuthorityScope
    annual_yield: Decimal
    yield_application_convention: YieldApplicationConvention
    valid_from: date
    valid_to: date | None
    fact_status: AmortizedCostSourceFactStatus
    source: AmortizedCostSourceMetadata

    def __post_init__(self) -> None:
        _require_scope(self.scope)
        _require_finite(self.annual_yield, "annual_yield")
        if not isinstance(self.yield_application_convention, YieldApplicationConvention):
            raise TypeError("yield_application_convention must be a YieldApplicationConvention")
        if self.yield_application_convention is YieldApplicationConvention.PER_PERIOD_EFFECTIVE:
            raise ValueError("per-period rates belong to the authoritative schedule fact")
        if (
            self.yield_application_convention is YieldApplicationConvention.ANNUAL_EFFECTIVE
            and self.annual_yield <= Decimal(-1)
        ):
            raise ValueError("annual effective yield must be greater than negative one")
        _require_fact_window(self.valid_from, self.valid_to)
        _require_fact_status(self.fact_status)
        _require_source(self.source)

    @property
    def source_record_key(self) -> tuple[str, str, str, str, str, str, str]:
        return (*self.scope.key, self.source.source_system, self.source.source_record_id)

    def is_effective_on(self, effective_date: date) -> bool:
        return _is_effective_on(self.valid_from, self.valid_to, effective_date)

    def content_hash(self) -> str:
        """Bind the supplied yield and its explicit interpretation."""

        return _fact_content_hash(
            fact_type="LOT_EFFECTIVE_YIELD",
            scope=self.scope,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            fact_status=self.fact_status,
            source=self.source,
            economics={
                "annual_yield": self.annual_yield,
                "yield_application_convention": self.yield_application_convention,
            },
        )

    def source_reference(self) -> FinancialSourceReference:
        return _source_reference(self.source, self.content_hash())


@dataclass(frozen=True, slots=True)
class LotAmortizationScheduleFact:
    """Authoritative contractual cashflow and rate schedule for one source lot."""

    scope: LotBookCostAuthorityScope
    schedule_version: int
    year_fraction_method_id: str
    year_fraction_method_version: int
    periods: tuple[AmortizationPeriodInput, ...]
    valid_from: date
    valid_to: date | None
    fact_status: AmortizedCostSourceFactStatus
    source: AmortizedCostSourceMetadata

    def __post_init__(self) -> None:
        _require_scope(self.scope)
        _require_positive_integer(self.schedule_version, "schedule_version")
        object.__setattr__(
            self,
            "year_fraction_method_id",
            _normalize_nonblank_string(
                self.year_fraction_method_id,
                "year_fraction_method_id",
            ),
        )
        _require_positive_integer(
            self.year_fraction_method_version,
            "year_fraction_method_version",
        )
        if not isinstance(self.periods, tuple):
            raise TypeError("periods must be a tuple")
        if not self.periods:
            raise ValueError("periods must not be empty")
        for index, period in enumerate(self.periods):
            if not isinstance(period, AmortizationPeriodInput):
                raise TypeError("periods must contain AmortizationPeriodInput values")
            if index and self.periods[index - 1].period_end_date != period.period_start_date:
                raise ValueError("periods must be contiguous and ordered")
        _require_fact_window(self.valid_from, self.valid_to)
        _require_fact_status(self.fact_status)
        _require_source(self.source)

    @property
    def source_record_key(self) -> tuple[str, str, str, str, str, str, str]:
        return (*self.scope.key, self.source.source_system, self.source.source_record_id)

    def is_effective_on(self, effective_date: date) -> bool:
        return _is_effective_on(self.valid_from, self.valid_to, effective_date)

    def content_hash(self) -> str:
        """Bind every authoritative period, cash coupon, rate, and year fraction."""

        return _fact_content_hash(
            fact_type="LOT_AMORTIZATION_SCHEDULE",
            scope=self.scope,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            fact_status=self.fact_status,
            source=self.source,
            economics={
                "periods": [
                    {
                        "cash_coupon_local": period.cash_coupon_local,
                        "period_end_date": period.period_end_date,
                        "period_start_date": period.period_start_date,
                        "supplied_period_rate": period.supplied_period_rate,
                        "year_fraction": period.year_fraction,
                    }
                    for period in self.periods
                ],
                "schedule_version": self.schedule_version,
                "year_fraction_method_id": self.year_fraction_method_id,
                "year_fraction_method_version": self.year_fraction_method_version,
            },
        )

    def source_reference(self) -> FinancialSourceReference:
        return _source_reference(self.source, self.content_hash())


def _fact_content_hash(
    *,
    fact_type: str,
    scope: LotBookCostAuthorityScope,
    valid_from: date,
    valid_to: date | None,
    fact_status: AmortizedCostSourceFactStatus,
    source: AmortizedCostSourceMetadata,
    economics: dict[str, object],
) -> str:
    return cast(
        str,
        canonical_content_hash(
            {
                "economics": economics,
                "fact_status": fact_status,
                "fact_type": fact_type,
                "scope": {
                    "legal_book_id": scope.legal_book_id,
                    "lot_id": scope.lot_id,
                    "portfolio_id": scope.portfolio_id,
                    "security_id": scope.security_id,
                    "tenant_id": scope.tenant_id,
                },
                "source": source.lineage_payload(),
                "valid_from": valid_from,
                "valid_to": valid_to,
            }
        ),
    )


def _source_reference(
    source: AmortizedCostSourceMetadata,
    content_hash: str,
) -> FinancialSourceReference:
    return FinancialSourceReference(
        source_system=source.source_system,
        source_record_id=source.source_record_id,
        source_revision=source.source_revision,
        source_content_hash=content_hash,
        observed_at=source.observed_at,
    )


def _require_scope(scope: object) -> None:
    if not isinstance(scope, LotBookCostAuthorityScope):
        raise TypeError("scope must be a LotBookCostAuthorityScope")


def _normalize_nonblank_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    return normalized


def _require_source(source: object) -> None:
    if not isinstance(source, AmortizedCostSourceMetadata):
        raise TypeError("source must be an AmortizedCostSourceMetadata")


def _require_fact_status(status: object) -> None:
    if not isinstance(status, AmortizedCostSourceFactStatus):
        raise TypeError("fact_status must be an AmortizedCostSourceFactStatus")


def _require_fact_window(valid_from: date, valid_to: date | None) -> None:
    if type(valid_from) is not date:
        raise TypeError("valid_from must be a date")
    if valid_to is not None and type(valid_to) is not date:
        raise TypeError("valid_to must be a date or None")
    if valid_to is not None and valid_to < valid_from:
        raise ValueError("valid_to must be on or after valid_from")


def _is_effective_on(valid_from: date, valid_to: date | None, effective_date: date) -> bool:
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date")
    return valid_from <= effective_date and (valid_to is None or valid_to >= effective_date)


def _require_positive_integer(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")


def _require_finite(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


def _require_nonnegative_finite(value: object, field_name: str) -> None:
    _require_finite(value, field_name)
    if cast(Decimal, value) < 0:
        raise ValueError(f"{field_name} must be nonnegative")
