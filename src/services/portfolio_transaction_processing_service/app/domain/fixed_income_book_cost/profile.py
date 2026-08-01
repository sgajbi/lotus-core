"""Immutable lot amortized-cost profile and period-ledger materialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    FinancialSourceReference,
    calculation_lineage_binds_output,
    canonical_content_hash,
    require_sha256_digest,
)

from .authority import LotBookCostAuthorityScope
from .calculation import (
    AmortizationPeriodResult,
    amortized_cost_schedule_output_payload,
    calculate_amortized_cost_schedule,
)
from .policy import (
    AmortizedCostDirection,
    AmortizedCostEligibilityReason,
    AmortizedCostProfileStatus,
)
from .resolution import ResolvedLotAmortizedCostInputs

LOT_AMORTIZED_COST_PROFILE_ID_VERSION = 1


@dataclass(frozen=True, slots=True)
class LotAmortizedCostPeriodLedgerEntry:
    """One immutable normalized recognition period for a profile version."""

    profile_id: str
    profile_version: int
    period_ordinal: int
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
    calculation_output_hash: str

    def __post_init__(self) -> None:
        _require_nonblank(self.profile_id, "profile_id")
        _require_positive_integer(self.profile_version, "profile_version")
        _require_positive_integer(self.period_ordinal, "period_ordinal")
        if type(self.period_start_date) is not date:
            raise TypeError("period_start_date must be a date")
        if type(self.period_end_date) is not date:
            raise TypeError("period_end_date must be a date")
        if self.period_end_date <= self.period_start_date:
            raise ValueError("period_end_date must be after period_start_date")
        for field_name in (
            "year_fraction",
            "begin_amortized_cost_local",
            "interest_income_local",
            "cash_coupon_local",
            "amortization_amount_local",
            "end_amortized_cost_local",
            "rounding_adjustment_local",
        ):
            _require_finite_decimal(getattr(self, field_name), field_name)
        if self.year_fraction <= 0:
            raise ValueError("year_fraction must be positive")
        for field_name in (
            "begin_amortized_cost_local",
            "cash_coupon_local",
            "end_amortized_cost_local",
        ):
            if cast(Decimal, getattr(self, field_name)) < 0:
                raise ValueError(f"{field_name} must be nonnegative")
        if self.period_rate is not None:
            _require_finite_decimal(self.period_rate, "period_rate")
        require_sha256_digest(self.calculation_output_hash, "calculation_output_hash")

    def content_hash(self) -> str:
        """Return deterministic evidence for this normalized period row."""

        return cast(
            str,
            canonical_content_hash(
                {
                    "amortization_amount_local": self.amortization_amount_local,
                    "begin_amortized_cost_local": self.begin_amortized_cost_local,
                    "calculation_output_hash": self.calculation_output_hash,
                    "cash_coupon_local": self.cash_coupon_local,
                    "end_amortized_cost_local": self.end_amortized_cost_local,
                    "interest_income_local": self.interest_income_local,
                    "period_end_date": self.period_end_date,
                    "period_ordinal": self.period_ordinal,
                    "period_rate": self.period_rate,
                    "period_start_date": self.period_start_date,
                    "profile_id": self.profile_id,
                    "profile_version": self.profile_version,
                    "rounding_adjustment_local": self.rounding_adjustment_local,
                    "year_fraction": self.year_fraction,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class LotAmortizedCostProfileVersion:
    """One append-only active or parked lot amortized-cost profile version."""

    profile_id: str
    profile_version: int
    scope: LotBookCostAuthorityScope
    effective_date: date
    status: AmortizedCostProfileStatus
    eligibility_reason: AmortizedCostEligibilityReason | None
    policy_id: str | None
    policy_version: int | None
    schedule_version: int | None
    currency: str | None
    direction: AmortizedCostDirection | None
    initial_amortized_cost_local: Decimal | None
    redemption_value_local: Decimal | None
    final_amortized_cost_local: Decimal | None
    residual_local: Decimal | None
    authority_content_hash: str | None
    source_references: tuple[FinancialSourceReference, ...]
    calculation_lineage: CalculationLineage | None
    periods: tuple[LotAmortizedCostPeriodLedgerEntry, ...]

    def __post_init__(self) -> None:
        _require_nonblank(self.profile_id, "profile_id")
        _require_positive_integer(self.profile_version, "profile_version")
        if not isinstance(self.scope, LotBookCostAuthorityScope):
            raise TypeError("scope must be a LotBookCostAuthorityScope")
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date")
        if not isinstance(self.status, AmortizedCostProfileStatus):
            raise TypeError("status must be an AmortizedCostProfileStatus")
        if not isinstance(self.source_references, tuple):
            raise TypeError("source_references must be a tuple")
        if not all(
            isinstance(reference, FinancialSourceReference) for reference in self.source_references
        ):
            raise TypeError("source_references must contain FinancialSourceReference values")
        if not isinstance(self.periods, tuple):
            raise TypeError("periods must be a tuple")
        if self.status is AmortizedCostProfileStatus.ACTIVE:
            self._validate_active()
        elif self.status in {
            AmortizedCostProfileStatus.PARKED,
            AmortizedCostProfileStatus.INELIGIBLE,
        }:
            self._validate_nonactive()
        else:
            raise ValueError("new profile materialization must be ACTIVE, PARKED, or INELIGIBLE")

    def _validate_active(self) -> None:
        if self.eligibility_reason is not None:
            raise ValueError("active profile must not declare an eligibility reason")
        for field_name in ("policy_id", "currency", "authority_content_hash"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"active profile requires {field_name}")
        for field_name in ("policy_version", "schedule_version"):
            value = getattr(self, field_name)
            if value is None:
                raise ValueError(f"active profile requires {field_name}")
            _require_positive_integer(value, field_name)
        if not isinstance(self.direction, AmortizedCostDirection):
            raise ValueError("active profile requires direction")
        for field_name in (
            "initial_amortized_cost_local",
            "redemption_value_local",
            "final_amortized_cost_local",
        ):
            value = getattr(self, field_name)
            if value is None:
                raise ValueError(f"active profile requires {field_name}")
            _require_finite_decimal(value, field_name)
            if cast(Decimal, value) < 0:
                raise ValueError(f"{field_name} must be nonnegative")
        if self.residual_local is None:
            raise ValueError("active profile requires residual_local")
        _require_finite_decimal(self.residual_local, "residual_local")
        if not self.source_references:
            raise ValueError("active profile requires source references")
        if not isinstance(self.calculation_lineage, CalculationLineage):
            raise ValueError("active profile requires calculation lineage")
        if not self.periods:
            raise ValueError("active profile requires period rows")
        require_sha256_digest(
            cast(str, self.authority_content_hash),
            "authority_content_hash",
        )
        for ordinal, period in enumerate(self.periods, start=1):
            if not isinstance(period, LotAmortizedCostPeriodLedgerEntry):
                raise TypeError("periods must contain LotAmortizedCostPeriodLedgerEntry values")
            if (
                period.profile_id != self.profile_id
                or period.profile_version != self.profile_version
                or period.period_ordinal != ordinal
            ):
                raise ValueError("period rows must match profile identity and contiguous ordinal")
            if period.calculation_output_hash != self.calculation_lineage.output_content_hash:
                raise ValueError("period row must bind the profile calculation output hash")
            if (
                ordinal > 1
                and self.periods[ordinal - 2].period_end_date != period.period_start_date
            ):
                raise ValueError("period rows must be contiguous and ordered")
        if self.periods[0].begin_amortized_cost_local != self.initial_amortized_cost_local:
            raise ValueError("first period must begin at the profile initial amortized cost")
        if self.periods[-1].end_amortized_cost_local != self.final_amortized_cost_local:
            raise ValueError("last period must end at the profile final amortized cost")
        output_payload = amortized_cost_schedule_output_payload(
            direction=self.direction,
            initial=cast(Decimal, self.initial_amortized_cost_local),
            redemption=cast(Decimal, self.redemption_value_local),
            final=cast(Decimal, self.final_amortized_cost_local),
            residual=cast(Decimal, self.residual_local),
            periods=tuple(_period_result_from_ledger_entry(period) for period in self.periods),
        )
        if not calculation_lineage_binds_output(
            self.calculation_lineage,
            output_payload=output_payload,
        ):
            raise ValueError("profile economics do not match calculation lineage")

    def _validate_nonactive(self) -> None:
        if not isinstance(self.eligibility_reason, AmortizedCostEligibilityReason):
            raise ValueError("non-active profile requires an eligibility reason")
        if self.periods:
            raise ValueError("non-active profile must not contain calculated period rows")
        if self.calculation_lineage is not None:
            raise ValueError("non-active profile must not contain calculation lineage")
        for field_name in (
            "direction",
            "initial_amortized_cost_local",
            "redemption_value_local",
            "final_amortized_cost_local",
            "residual_local",
        ):
            if getattr(self, field_name) is not None:
                raise ValueError(f"non-active profile must not contain {field_name}")
        if self.authority_content_hash is not None:
            require_sha256_digest(self.authority_content_hash, "authority_content_hash")

    def content_hash(self) -> str:
        """Bind lifecycle, source, calculation, and every period row."""

        return cast(
            str,
            canonical_content_hash(
                {
                    "authority_content_hash": self.authority_content_hash,
                    "calculation_lineage": (
                        self.calculation_lineage.lineage_payload()
                        if self.calculation_lineage is not None
                        else None
                    ),
                    "currency": self.currency,
                    "direction": self.direction,
                    "effective_date": self.effective_date,
                    "eligibility_reason": self.eligibility_reason,
                    "final_amortized_cost_local": self.final_amortized_cost_local,
                    "initial_amortized_cost_local": self.initial_amortized_cost_local,
                    "period_content_hashes": [period.content_hash() for period in self.periods],
                    "policy_id": self.policy_id,
                    "policy_version": self.policy_version,
                    "profile_id": self.profile_id,
                    "profile_version": self.profile_version,
                    "redemption_value_local": self.redemption_value_local,
                    "residual_local": self.residual_local,
                    "schedule_version": self.schedule_version,
                    "scope": self.scope.key,
                    "source_references": [
                        reference.lineage_payload() for reference in self.source_references
                    ],
                    "status": self.status,
                }
            ),
        )


def lot_amortized_cost_profile_id(scope: LotBookCostAuthorityScope) -> str:
    """Return stable version-independent identity for one exact source lot."""

    if not isinstance(scope, LotBookCostAuthorityScope):
        raise TypeError("scope must be a LotBookCostAuthorityScope")
    identity_hash = canonical_content_hash(
        {
            "identity_version": LOT_AMORTIZED_COST_PROFILE_ID_VERSION,
            "profile_type": "LOT_AMORTIZED_COST",
            "scope": scope.key,
        }
    )
    return f"lot-amortized-cost:{identity_hash}"


def materialize_active_lot_amortized_cost_profile(
    resolved: ResolvedLotAmortizedCostInputs,
    *,
    profile_version: int,
) -> LotAmortizedCostProfileVersion:
    """Calculate and materialize one complete append-only active profile version."""

    if not isinstance(resolved, ResolvedLotAmortizedCostInputs):
        raise TypeError("resolved must be a ResolvedLotAmortizedCostInputs")
    _require_positive_integer(profile_version, "profile_version")
    result = calculate_amortized_cost_schedule(
        policy=resolved.policy,
        inputs=resolved.calculation_inputs,
    )
    profile_id = lot_amortized_cost_profile_id(resolved.assignment.scope)
    periods = tuple(
        _materialize_period(
            profile_id=profile_id,
            profile_version=profile_version,
            period_ordinal=ordinal,
            result=period,
            calculation_output_hash=result.lineage.output_content_hash,
        )
        for ordinal, period in enumerate(result.periods, start=1)
    )
    return LotAmortizedCostProfileVersion(
        profile_id=profile_id,
        profile_version=profile_version,
        scope=resolved.assignment.scope,
        effective_date=resolved.cache_key.effective_date,
        status=AmortizedCostProfileStatus.ACTIVE,
        eligibility_reason=None,
        policy_id=resolved.policy.policy_id,
        policy_version=resolved.policy.policy_version,
        schedule_version=resolved.schedule_fact.schedule_version,
        currency=resolved.basis_fact.currency,
        direction=result.direction,
        initial_amortized_cost_local=result.initial_amortized_cost_local,
        redemption_value_local=result.redemption_value_local,
        final_amortized_cost_local=result.final_amortized_cost_local,
        residual_local=result.residual_local,
        authority_content_hash=resolved.cache_key.authority_content_hash,
        source_references=resolved.source_references,
        calculation_lineage=result.lineage,
        periods=periods,
    )


def materialize_parked_lot_amortized_cost_profile(
    *,
    scope: LotBookCostAuthorityScope,
    effective_date: date,
    profile_version: int,
    reason: AmortizedCostEligibilityReason,
    authority_content_hash: str | None = None,
    source_references: tuple[FinancialSourceReference, ...] = (),
) -> LotAmortizedCostProfileVersion:
    """Materialize a durable fail-closed profile without invented economics."""

    if not isinstance(scope, LotBookCostAuthorityScope):
        raise TypeError("scope must be a LotBookCostAuthorityScope")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date")
    _require_positive_integer(profile_version, "profile_version")
    if not isinstance(reason, AmortizedCostEligibilityReason):
        raise TypeError("reason must be an AmortizedCostEligibilityReason")
    return LotAmortizedCostProfileVersion(
        profile_id=lot_amortized_cost_profile_id(scope),
        profile_version=profile_version,
        scope=scope,
        effective_date=effective_date,
        status=AmortizedCostProfileStatus.PARKED,
        eligibility_reason=reason,
        policy_id=None,
        policy_version=None,
        schedule_version=None,
        currency=None,
        direction=None,
        initial_amortized_cost_local=None,
        redemption_value_local=None,
        final_amortized_cost_local=None,
        residual_local=None,
        authority_content_hash=authority_content_hash,
        source_references=source_references,
        calculation_lineage=None,
        periods=(),
    )


def _materialize_period(
    *,
    profile_id: str,
    profile_version: int,
    period_ordinal: int,
    result: AmortizationPeriodResult,
    calculation_output_hash: str,
) -> LotAmortizedCostPeriodLedgerEntry:
    return LotAmortizedCostPeriodLedgerEntry(
        profile_id=profile_id,
        profile_version=profile_version,
        period_ordinal=period_ordinal,
        period_start_date=result.period_start_date,
        period_end_date=result.period_end_date,
        year_fraction=result.year_fraction,
        period_rate=result.period_rate,
        begin_amortized_cost_local=result.begin_amortized_cost_local,
        interest_income_local=result.interest_income_local,
        cash_coupon_local=result.cash_coupon_local,
        amortization_amount_local=result.amortization_amount_local,
        end_amortized_cost_local=result.end_amortized_cost_local,
        rounding_adjustment_local=result.rounding_adjustment_local,
        calculation_output_hash=calculation_output_hash,
    )


def _period_result_from_ledger_entry(
    period: LotAmortizedCostPeriodLedgerEntry,
) -> AmortizationPeriodResult:
    return AmortizationPeriodResult(
        period_start_date=period.period_start_date,
        period_end_date=period.period_end_date,
        year_fraction=period.year_fraction,
        period_rate=period.period_rate,
        begin_amortized_cost_local=period.begin_amortized_cost_local,
        interest_income_local=period.interest_income_local,
        cash_coupon_local=period.cash_coupon_local,
        amortization_amount_local=period.amortization_amount_local,
        end_amortized_cost_local=period.end_amortized_cost_local,
        rounding_adjustment_local=period.rounding_adjustment_local,
    )


def _require_positive_integer(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be nonblank")


def _require_finite_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
