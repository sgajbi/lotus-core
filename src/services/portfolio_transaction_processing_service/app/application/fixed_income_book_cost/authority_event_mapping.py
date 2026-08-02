"""Map fixed-income book-cost transport authority into domain authority."""

from __future__ import annotations

from portfolio_common.event_contracts import (
    AmortizationScheduleAuthorityContract,
    CleanCostBasisAuthorityContract,
    EffectiveYieldAuthorityContract,
    FixedIncomeBookCostAuthorityEvent,
    FixedIncomeBookCostAuthorityScope,
    FixedIncomeBookCostAuthoritySource,
    PolicyAssignmentAuthorityContract,
)
from portfolio_common.event_contracts.fixed_income_book_cost import (
    FixedIncomeBookCostAuthorityStatus,
    FixedIncomeDiscountOrigin,
    FixedIncomeYieldApplication,
)

from ...domain.fixed_income_book_cost import (
    AmortizationPeriodInput,
    AmortizedCostAssignmentStatus,
    AmortizedCostSourceFactStatus,
    AmortizedCostSourceMetadata,
    DiscountOriginClassification,
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    LotEffectiveYieldFact,
    YieldApplicationConvention,
)
from ...ports import LotAmortizedCostAuthority


class UnsupportedFixedIncomeBookCostAuthorityMappingError(ValueError):
    """Reject authority vocabulary that the application does not explicitly support."""


_ASSIGNMENT_STATUS = {
    FixedIncomeBookCostAuthorityStatus.ACTIVE: AmortizedCostAssignmentStatus.ACTIVE,
    FixedIncomeBookCostAuthorityStatus.SUSPENDED: AmortizedCostAssignmentStatus.SUSPENDED,
    FixedIncomeBookCostAuthorityStatus.RETIRED: AmortizedCostAssignmentStatus.RETIRED,
}
_FACT_STATUS = {
    FixedIncomeBookCostAuthorityStatus.ACTIVE: AmortizedCostSourceFactStatus.ACTIVE,
    FixedIncomeBookCostAuthorityStatus.SUSPENDED: AmortizedCostSourceFactStatus.SUSPENDED,
    FixedIncomeBookCostAuthorityStatus.RETIRED: AmortizedCostSourceFactStatus.RETIRED,
}
_DISCOUNT_ORIGIN = {
    FixedIncomeDiscountOrigin.AT_PAR: DiscountOriginClassification.AT_PAR,
    FixedIncomeDiscountOrigin.PURCHASE_PREMIUM: DiscountOriginClassification.PURCHASE_PREMIUM,
    FixedIncomeDiscountOrigin.MARKET_DISCOUNT: DiscountOriginClassification.MARKET_DISCOUNT,
    FixedIncomeDiscountOrigin.ORIGINAL_ISSUE_DISCOUNT: (
        DiscountOriginClassification.ORIGINAL_ISSUE_DISCOUNT
    ),
}
_YIELD_APPLICATION = {
    FixedIncomeYieldApplication.ANNUAL_EFFECTIVE: YieldApplicationConvention.ANNUAL_EFFECTIVE,
    FixedIncomeYieldApplication.ANNUAL_NOMINAL_SIMPLE: (
        YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE
    ),
}


def map_fixed_income_book_cost_authority_event(
    event: FixedIncomeBookCostAuthorityEvent,
) -> LotAmortizedCostAuthority:
    """Return one exact-scope domain authority without transport fallbacks."""

    if not isinstance(event, FixedIncomeBookCostAuthorityEvent):
        raise TypeError("event must be a FixedIncomeBookCostAuthorityEvent")
    authority = event.authority
    if not isinstance(
        authority,
        (
            PolicyAssignmentAuthorityContract,
            CleanCostBasisAuthorityContract,
            AmortizationScheduleAuthorityContract,
            EffectiveYieldAuthorityContract,
        ),
    ):
        raise UnsupportedFixedIncomeBookCostAuthorityMappingError(
            f"unsupported fixed-income book-cost authority contract: {type(authority).__name__}"
        )
    scope = _map_scope(authority.header.scope)
    if isinstance(authority, PolicyAssignmentAuthorityContract):
        return LotAmortizedCostPolicyAssignment(
            scope=scope,
            policy_id=authority.policy_id,
            policy_version=authority.policy_version,
            valid_from=authority.header.valid_from,
            valid_to=authority.header.valid_to,
            assignment_status=_map_assignment_status(authority.header.status),
            assignment_version=authority.header.source.source_version,
            source_system=authority.header.source.source_system,
            source_record_id=authority.header.source.source_record_id,
            source_revision=authority.header.source.source_revision,
            observed_at=authority.header.source.observed_at,
            assignment_reason=authority.assignment_reason,
        )
    source = _map_source(authority.header.source)
    fact_status = _map_fact_status(authority.header.status)
    if isinstance(authority, CleanCostBasisAuthorityContract):
        return LotAmortizedCostBasisFact(
            scope=scope,
            currency=authority.currency,
            initial_clean_cost_local=authority.initial_clean_cost_local,
            fees_in_basis_local=authority.fees_in_basis_local,
            redemption_value_local=authority.redemption_value_local,
            discount_origin=_map_discount_origin(authority.discount_origin),
            valid_from=authority.header.valid_from,
            valid_to=authority.header.valid_to,
            fact_status=fact_status,
            source=source,
        )
    if isinstance(authority, AmortizationScheduleAuthorityContract):
        return LotAmortizationScheduleFact(
            scope=scope,
            schedule_version=authority.schedule_version,
            year_fraction_method_id=authority.year_fraction_method_id,
            year_fraction_method_version=authority.year_fraction_method_version,
            periods=tuple(
                AmortizationPeriodInput(
                    period_start_date=period.period_start_date,
                    period_end_date=period.period_end_date,
                    year_fraction=period.year_fraction,
                    cash_coupon_local=period.cash_coupon_local,
                    supplied_period_rate=period.supplied_period_rate,
                )
                for period in authority.periods
            ),
            valid_from=authority.header.valid_from,
            valid_to=authority.header.valid_to,
            fact_status=fact_status,
            source=source,
        )
    if isinstance(authority, EffectiveYieldAuthorityContract):
        return LotEffectiveYieldFact(
            scope=scope,
            annual_yield=authority.annual_yield,
            yield_application_convention=_map_yield_application(authority.yield_application),
            valid_from=authority.header.valid_from,
            valid_to=authority.header.valid_to,
            fact_status=fact_status,
            source=source,
        )
    raise AssertionError("supported authority contract was not mapped")


def _map_scope(source_scope: object) -> LotBookCostAuthorityScope:
    if not isinstance(source_scope, FixedIncomeBookCostAuthorityScope):
        raise UnsupportedFixedIncomeBookCostAuthorityMappingError(
            "authority scope must use FixedIncomeBookCostAuthorityScope"
        )
    return LotBookCostAuthorityScope(
        tenant_id=source_scope.tenant_id,
        legal_book_id=source_scope.legal_book_id,
        portfolio_id=source_scope.portfolio_id,
        security_id=source_scope.security_id,
        lot_id=source_scope.lot_id,
    )


def _map_source(source: object) -> AmortizedCostSourceMetadata:
    if not isinstance(source, FixedIncomeBookCostAuthoritySource):
        raise UnsupportedFixedIncomeBookCostAuthorityMappingError(
            "authority source must use FixedIncomeBookCostAuthoritySource"
        )
    return AmortizedCostSourceMetadata(
        source_system=source.source_system,
        source_record_id=source.source_record_id,
        source_revision=source.source_revision,
        fact_version=source.source_version,
        observed_at=source.observed_at,
    )


def _map_assignment_status(
    status: object,
) -> AmortizedCostAssignmentStatus:
    try:
        return _ASSIGNMENT_STATUS[status]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise UnsupportedFixedIncomeBookCostAuthorityMappingError(
            f"unsupported assignment authority status: {status!r}"
        ) from exc


def _map_fact_status(status: object) -> AmortizedCostSourceFactStatus:
    try:
        return _FACT_STATUS[status]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise UnsupportedFixedIncomeBookCostAuthorityMappingError(
            f"unsupported fact authority status: {status!r}"
        ) from exc


def _map_discount_origin(origin: object) -> DiscountOriginClassification:
    try:
        return _DISCOUNT_ORIGIN[origin]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise UnsupportedFixedIncomeBookCostAuthorityMappingError(
            f"unsupported discount origin: {origin!r}"
        ) from exc


def _map_yield_application(application: object) -> YieldApplicationConvention:
    try:
        return _YIELD_APPLICATION[application]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise UnsupportedFixedIncomeBookCostAuthorityMappingError(
            f"unsupported yield application: {application!r}"
        ) from exc
