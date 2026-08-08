"""Verify the fixed-income authority transport-to-domain boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.event_contracts import (
    EffectiveYieldAuthorityContract,
    FixedIncomeBookCostAuthorityEvent,
    FixedIncomeBookCostAuthorityHeader,
)
from portfolio_common.event_contracts.fixed_income_book_cost import (
    FixedIncomeYieldApplication,
)

from src.services.portfolio_transaction_processing_service.app.application.fixed_income_book_cost import (  # noqa: E501
    UnsupportedFixedIncomeBookCostAuthorityMappingError,
    map_fixed_income_book_cost_authority_event,
)
from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (  # noqa: E501
    AmortizedCostAssignmentStatus,
    AmortizedCostSourceFactStatus,
    DiscountOriginClassification,
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotAmortizedCostPolicyAssignment,
    LotEffectiveYieldFact,
    YieldApplicationConvention,
)


def _header(*, status: str = "ACTIVE", source_version: int = 3) -> dict[str, object]:
    return {
        "scope": {
            "tenant_id": "TENANT_SG",
            "legal_book_id": "BOOK_SG_PB",
            "portfolio_id": "PORTFOLIO_001",
            "security_id": "BOND_001",
            "lot_id": "LOT_001",
        },
        "source": {
            "source_system": "fixed_income_accounting_master",
            "source_record_id": "AUTHORITY_001",
            "source_revision": "revision-3",
            "source_version": source_version,
            "observed_at": "2026-01-02T10:30:00+08:00",
        },
        "status": status,
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
    }


def _event(authority: dict[str, object]) -> FixedIncomeBookCostAuthorityEvent:
    return FixedIncomeBookCostAuthorityEvent.model_validate(
        {
            "event_type": "fixed_income.book_cost.authority.received",
            "schema_version": "1.0.0",
            "authority": authority,
        }
    )


def _basis_authority(*, status: str = "ACTIVE") -> dict[str, object]:
    return {
        "authority_type": "CLEAN_COST_BASIS",
        "header": _header(status=status),
        "currency": "sgd",
        "initial_clean_cost_local": "97.0000000000",
        "fees_in_basis_local": "0.2500000000",
        "redemption_value_local": "100.0000000000",
        "discount_origin": "MARKET_DISCOUNT",
    }


def test_maps_policy_assignment_with_exact_scope_source_and_effective_window() -> None:
    mapped = map_fixed_income_book_cost_authority_event(
        _event(
            {
                "authority_type": "POLICY_ASSIGNMENT",
                "header": _header(source_version=7),
                "policy_id": "IFRS9_EIR_LOCAL",
                "policy_version": 2,
                "assignment_reason": "Approved book-cost treatment",
            }
        )
    )

    assert isinstance(mapped, LotAmortizedCostPolicyAssignment)
    assert mapped.scope.key == (
        "TENANT_SG",
        "BOOK_SG_PB",
        "PORTFOLIO_001",
        "BOND_001",
        "LOT_001",
    )
    assert mapped.policy_id == "IFRS9_EIR_LOCAL"
    assert mapped.policy_version == 2
    assert mapped.assignment_status is AmortizedCostAssignmentStatus.ACTIVE
    assert mapped.assignment_version == 7
    assert mapped.source_system == "fixed_income_accounting_master"
    assert mapped.source_record_id == "AUTHORITY_001"
    assert mapped.source_revision == "revision-3"
    assert mapped.observed_at == datetime(2026, 1, 2, 2, 30, tzinfo=UTC)
    assert mapped.valid_from == date(2026, 1, 1)
    assert mapped.valid_to == date(2026, 12, 31)
    assert mapped.assignment_reason == "Approved book-cost treatment"


def test_maps_clean_cost_basis_without_numeric_or_currency_drift() -> None:
    mapped = map_fixed_income_book_cost_authority_event(_event(_basis_authority()))

    assert isinstance(mapped, LotAmortizedCostBasisFact)
    assert mapped.currency == "SGD"
    assert mapped.initial_clean_cost_local == Decimal("97.0000000000")
    assert mapped.fees_in_basis_local == Decimal("0.2500000000")
    assert mapped.redemption_value_local == Decimal("100.0000000000")
    assert mapped.discount_origin is DiscountOriginClassification.MARKET_DISCOUNT
    assert mapped.fact_status is AmortizedCostSourceFactStatus.ACTIVE
    assert mapped.source.fact_version == 3
    assert mapped.valid_from == date(2026, 1, 1)
    assert mapped.valid_to == date(2026, 12, 31)


def test_maps_complete_schedule_and_preserves_supplied_period_rate() -> None:
    mapped = map_fixed_income_book_cost_authority_event(
        _event(
            {
                "authority_type": "AMORTIZATION_SCHEDULE",
                "header": _header(),
                "schedule_version": 9,
                "year_fraction_method_id": "ACTUAL_ACTUAL_ICMA",
                "year_fraction_method_version": 2,
                "periods": [
                    {
                        "period_start_date": "2026-01-01",
                        "period_end_date": "2026-07-01",
                        "year_fraction": "0.5",
                        "cash_coupon_local": "2.0",
                        "supplied_period_rate": "0.025",
                    },
                    {
                        "period_start_date": "2026-07-01",
                        "period_end_date": "2027-01-01",
                        "year_fraction": "0.5",
                        "cash_coupon_local": "2.0",
                        "supplied_period_rate": "0.026",
                    },
                ],
            }
        )
    )

    assert isinstance(mapped, LotAmortizationScheduleFact)
    assert mapped.schedule_version == 9
    assert mapped.year_fraction_method_id == "ACTUAL_ACTUAL_ICMA"
    assert mapped.year_fraction_method_version == 2
    assert tuple(period.supplied_period_rate for period in mapped.periods) == (
        Decimal("0.025"),
        Decimal("0.026"),
    )
    assert mapped.periods[0].period_end_date == mapped.periods[1].period_start_date
    assert mapped.source.fact_version == 3


def test_maps_effective_yield_and_explicit_application_convention() -> None:
    mapped = map_fixed_income_book_cost_authority_event(
        _event(
            {
                "authority_type": "EFFECTIVE_YIELD",
                "header": _header(),
                "annual_yield": "0.05125",
                "yield_application": "ANNUAL_NOMINAL_SIMPLE",
            }
        )
    )

    assert isinstance(mapped, LotEffectiveYieldFact)
    assert mapped.annual_yield == Decimal("0.05125")
    assert mapped.yield_application_convention is YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE
    assert mapped.source.fact_version == 3


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("ACTIVE", AmortizedCostSourceFactStatus.ACTIVE),
        ("SUSPENDED", AmortizedCostSourceFactStatus.SUSPENDED),
        ("RETIRED", AmortizedCostSourceFactStatus.RETIRED),
    ],
)
def test_maps_every_source_lifecycle_status(
    status: str,
    expected: AmortizedCostSourceFactStatus,
) -> None:
    mapped = map_fixed_income_book_cost_authority_event(_event(_basis_authority(status=status)))

    assert isinstance(mapped, LotAmortizedCostBasisFact)
    assert mapped.fact_status is expected


def test_rejects_unrecognized_authority_contract_even_after_validation_bypass() -> None:
    event = FixedIncomeBookCostAuthorityEvent.model_construct(authority=object())

    with pytest.raises(
        UnsupportedFixedIncomeBookCostAuthorityMappingError,
        match="unsupported fixed-income book-cost authority contract",
    ):
        map_fixed_income_book_cost_authority_event(event)


def test_rejects_unrecognized_status_even_after_validation_bypass() -> None:
    valid = _event(_basis_authority())
    header = FixedIncomeBookCostAuthorityHeader.model_construct(
        scope=valid.authority.header.scope,
        source=valid.authority.header.source,
        status="UNKNOWN",
        valid_from=date(2026, 1, 1),
        valid_to=None,
    )
    authority = valid.authority.model_copy(update={"header": header})
    event = valid.model_copy(update={"authority": authority})

    with pytest.raises(
        UnsupportedFixedIncomeBookCostAuthorityMappingError,
        match="unsupported fact authority status",
    ):
        map_fixed_income_book_cost_authority_event(event)


def test_rejects_per_period_yield_authority_after_validation_bypass() -> None:
    valid = _event(
        {
            "authority_type": "EFFECTIVE_YIELD",
            "header": _header(),
            "annual_yield": "0.05",
            "yield_application": "ANNUAL_EFFECTIVE",
        }
    )
    assert isinstance(valid.authority, EffectiveYieldAuthorityContract)
    authority = valid.authority.model_copy(
        update={"yield_application": FixedIncomeYieldApplication.PER_PERIOD_EFFECTIVE}
    )

    with pytest.raises(
        UnsupportedFixedIncomeBookCostAuthorityMappingError,
        match="unsupported yield application",
    ):
        map_fixed_income_book_cost_authority_event(
            valid.model_copy(update={"authority": authority})
        )
