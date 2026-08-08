"""Reusable authoritative fixed-income book-cost fixtures for repository tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (  # noqa: E501
    AmortizationPeriodInput,
    AmortizedCostAssignmentStatus,
    AmortizedCostMethod,
    AmortizedCostPolicy,
    AmortizedCostSourceFactStatus,
    AmortizedCostSourceMetadata,
    DiscountOriginClassification,
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    LotEffectiveYieldFact,
    ResolvedLotAmortizedCostInputs,
    YieldApplicationConvention,
    resolve_lot_amortized_cost_inputs,
)


def fixed_income_book_cost_scope() -> LotBookCostAuthorityScope:
    """Return one tenant-safe source-lot identity used only by isolated tests."""

    return LotBookCostAuthorityScope(
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="AMORT_PORTFOLIO",
        security_id="AMORT_BOND_001",
        lot_id="AMORT_LOT_001",
    )


def resolved_fixed_income_book_cost_inputs() -> ResolvedLotAmortizedCostInputs:
    """Build a complete, source-referenced one-period effective-yield authority bundle."""

    scope = fixed_income_book_cost_scope()
    policy = AmortizedCostPolicy(
        policy_id="IFRS9_EIR_LOCAL",
        policy_version=1,
        method=AmortizedCostMethod.EFFECTIVE_YIELD,
        yield_application_convention=YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE,
        include_fees_in_amortized_cost=True,
        residual_tolerance_local=Decimal("0.0000000001"),
    )
    return resolve_lot_amortized_cost_inputs(
        assignments=[
            LotAmortizedCostPolicyAssignment(
                scope=scope,
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                valid_from=date(2026, 1, 1),
                valid_to=None,
                assignment_status=AmortizedCostAssignmentStatus.ACTIVE,
                assignment_version=1,
                source_system="accounting_policy_master",
                source_record_id="AMORT_LOT_001_POLICY",
                source_revision="revision-1",
                observed_at=datetime(2026, 1, 1, 8, tzinfo=UTC),
                assignment_reason="Approved treatment",
            )
        ],
        basis_facts=[
            LotAmortizedCostBasisFact(
                scope=scope,
                currency="SGD",
                initial_clean_cost_local=Decimal("97"),
                fees_in_basis_local=Decimal("0"),
                redemption_value_local=Decimal("100"),
                discount_origin=DiscountOriginClassification.MARKET_DISCOUNT,
                valid_from=date(2026, 1, 1),
                valid_to=None,
                fact_status=AmortizedCostSourceFactStatus.ACTIVE,
                source=_source("AMORT_LOT_001_BASIS"),
            )
        ],
        schedule_facts=[
            LotAmortizationScheduleFact(
                scope=scope,
                schedule_version=2,
                year_fraction_method_id="ACTUAL_ACTUAL_ICMA",
                year_fraction_method_version=1,
                periods=(
                    AmortizationPeriodInput(
                        period_start_date=date(2026, 1, 1),
                        period_end_date=date(2027, 1, 1),
                        year_fraction=Decimal("1"),
                        cash_coupon_local=Decimal("2"),
                    ),
                ),
                valid_from=date(2026, 1, 1),
                valid_to=None,
                fact_status=AmortizedCostSourceFactStatus.ACTIVE,
                source=_source("AMORT_BOND_001_SCHEDULE"),
            )
        ],
        yield_facts=[
            LotEffectiveYieldFact(
                scope=scope,
                annual_yield=Decimal("0.05154639175257731958762886598"),
                yield_application_convention=YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE,
                valid_from=date(2026, 1, 1),
                valid_to=None,
                fact_status=AmortizedCostSourceFactStatus.ACTIVE,
                source=_source("AMORT_LOT_001_EIR"),
            )
        ],
        scope=scope,
        effective_date=date(2026, 1, 1),
        policy=policy,
    )


def _source(record_id: str) -> AmortizedCostSourceMetadata:
    return AmortizedCostSourceMetadata(
        source_system="fixed_income_accounting_master",
        source_record_id=record_id,
        source_revision="revision-1",
        fact_version=1,
        observed_at=datetime(2026, 1, 1, 8, tzinfo=UTC),
    )
