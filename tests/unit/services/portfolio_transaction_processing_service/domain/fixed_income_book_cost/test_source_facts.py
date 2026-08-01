"""Tests for source-versioned lot amortized-cost inputs."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AmortizationPeriodInput,
    AmortizedCostSourceFactStatus,
    AmortizedCostSourceMetadata,
    DiscountOriginClassification,
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotBookCostAuthorityScope,
    LotEffectiveYieldFact,
    YieldApplicationConvention,
)


def _scope() -> LotBookCostAuthorityScope:
    return LotBookCostAuthorityScope(
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="SEC_BOND_001",
        lot_id="LOT_BUY_001",
    )


def _source(**overrides: object) -> AmortizedCostSourceMetadata:
    values: dict[str, object] = {
        "source_system": "fixed_income_accounting_master",
        "source_record_id": "LOT_BUY_001_BOOK_COST",
        "source_revision": "revision-17",
        "fact_version": 1,
        "observed_at": datetime(2026, 1, 1, 8, tzinfo=UTC),
    }
    values.update(overrides)
    return AmortizedCostSourceMetadata(**values)  # type: ignore[arg-type]


def _period(
    start: date = date(2026, 1, 1),
    end: date = date(2027, 1, 1),
    *,
    rate: str | None = None,
) -> AmortizationPeriodInput:
    return AmortizationPeriodInput(
        period_start_date=start,
        period_end_date=end,
        year_fraction=Decimal("1"),
        cash_coupon_local=Decimal("3"),
        supplied_period_rate=Decimal(rate) if rate is not None else None,
    )


def _basis(**overrides: object) -> LotAmortizedCostBasisFact:
    values: dict[str, object] = {
        "scope": _scope(),
        "currency": "sgd",
        "initial_clean_cost_local": Decimal("92"),
        "fees_in_basis_local": Decimal("0"),
        "redemption_value_local": Decimal("100"),
        "discount_origin": DiscountOriginClassification.MARKET_DISCOUNT,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "fact_status": AmortizedCostSourceFactStatus.ACTIVE,
        "source": _source(),
    }
    values.update(overrides)
    return LotAmortizedCostBasisFact(**values)  # type: ignore[arg-type]


def test_clean_basis_fact_normalizes_currency_and_binds_complete_source_lineage() -> None:
    fact = _basis()

    assert fact.currency == "SGD"
    assert fact.is_effective_on(date(2026, 7, 18))
    assert len(fact.content_hash()) == 64
    assert fact.source_reference().source_content_hash == fact.content_hash()
    assert fact.source_record_key == (
        *_scope().key,
        fact.source.source_system,
        fact.source.source_record_id,
    )


@pytest.mark.parametrize(
    ("opening", "redemption", "classification"),
    [
        ("105", "100", DiscountOriginClassification.PURCHASE_PREMIUM),
        ("100", "100", DiscountOriginClassification.AT_PAR),
        ("92", "100", DiscountOriginClassification.MARKET_DISCOUNT),
        ("92", "100", DiscountOriginClassification.ORIGINAL_ISSUE_DISCOUNT),
    ],
)
def test_basis_classification_is_explicit_and_economically_consistent(
    opening: str,
    redemption: str,
    classification: DiscountOriginClassification,
) -> None:
    fact = _basis(
        initial_clean_cost_local=Decimal(opening),
        redemption_value_local=Decimal(redemption),
        discount_origin=classification,
    )

    assert fact.discount_origin is classification


def test_discount_origin_uses_clean_cost_without_policy_dependent_fee_treatment() -> None:
    fact = _basis(
        initial_clean_cost_local=Decimal("100"),
        fees_in_basis_local=Decimal("1"),
        redemption_value_local=Decimal("100"),
        discount_origin=DiscountOriginClassification.AT_PAR,
    )

    assert fact.discount_origin is DiscountOriginClassification.AT_PAR


@pytest.mark.parametrize(
    ("opening", "redemption", "classification", "message"),
    [
        ("105", "100", DiscountOriginClassification.MARKET_DISCOUNT, "premium basis"),
        ("100", "100", DiscountOriginClassification.PURCHASE_PREMIUM, "par basis"),
        ("92", "100", DiscountOriginClassification.AT_PAR, "discount basis"),
    ],
)
def test_basis_rejects_inferred_or_contradictory_discount_origin(
    opening: str,
    redemption: str,
    classification: DiscountOriginClassification,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _basis(
            initial_clean_cost_local=Decimal(opening),
            redemption_value_local=Decimal(redemption),
            discount_origin=classification,
        )


def test_annual_yield_fact_binds_convention_and_accepts_governed_negative_yield() -> None:
    fact = LotEffectiveYieldFact(
        scope=_scope(),
        annual_yield=Decimal("-0.005"),
        yield_application_convention=YieldApplicationConvention.ANNUAL_EFFECTIVE,
        valid_from=date(2026, 1, 1),
        valid_to=None,
        fact_status=AmortizedCostSourceFactStatus.ACTIVE,
        source=_source(source_record_id="LOT_BUY_001_EIR"),
    )

    assert fact.is_effective_on(date(2026, 7, 18))
    assert fact.source_reference().source_content_hash == fact.content_hash()


def test_yield_fact_rejects_per_period_rate_authority_and_invalid_effective_rate() -> None:
    values = {
        "scope": _scope(),
        "annual_yield": Decimal("0.03"),
        "yield_application_convention": YieldApplicationConvention.PER_PERIOD_EFFECTIVE,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "fact_status": AmortizedCostSourceFactStatus.ACTIVE,
        "source": _source(source_record_id="LOT_BUY_001_EIR"),
    }
    with pytest.raises(ValueError, match="belong to the authoritative schedule"):
        LotEffectiveYieldFact(**values)  # type: ignore[arg-type]
    values["yield_application_convention"] = YieldApplicationConvention.ANNUAL_EFFECTIVE
    values["annual_yield"] = Decimal("-1")
    with pytest.raises(ValueError, match="greater than negative one"):
        LotEffectiveYieldFact(**values)  # type: ignore[arg-type]


def test_schedule_fact_binds_ordered_period_economics_and_source_version() -> None:
    fact = LotAmortizationScheduleFact(
        scope=_scope(),
        schedule_version=2,
        year_fraction_method_id="ACTUAL_ACTUAL_ICMA",
        year_fraction_method_version=1,
        periods=(
            _period(end=date(2026, 7, 1), rate="0.02"),
            _period(start=date(2026, 7, 1), rate="0.025"),
        ),
        valid_from=date(2026, 1, 1),
        valid_to=None,
        fact_status=AmortizedCostSourceFactStatus.ACTIVE,
        source=_source(source_record_id="SEC_BOND_001_SCHEDULE", fact_version=3),
    )

    assert fact.schedule_version == 2
    assert fact.source.fact_version == 3
    assert fact.is_effective_on(date(2026, 7, 18))
    assert fact.source_reference().source_content_hash == fact.content_hash()


def test_schedule_fact_rejects_gaps_and_non_period_values() -> None:
    values: dict[str, object] = {
        "scope": _scope(),
        "schedule_version": 1,
        "year_fraction_method_id": "ACTUAL_ACTUAL_ICMA",
        "year_fraction_method_version": 1,
        "periods": (
            _period(end=date(2026, 7, 1)),
            _period(start=date(2026, 7, 2)),
        ),
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "fact_status": AmortizedCostSourceFactStatus.ACTIVE,
        "source": _source(source_record_id="SEC_BOND_001_SCHEDULE"),
    }
    with pytest.raises(ValueError, match="contiguous"):
        LotAmortizationScheduleFact(**values)  # type: ignore[arg-type]
    values["periods"] = (object(),)
    with pytest.raises(TypeError, match="AmortizationPeriodInput"):
        LotAmortizationScheduleFact(**values)  # type: ignore[arg-type]


def test_source_fact_hash_changes_for_economic_or_source_version_correction() -> None:
    baseline = _basis()
    economics_correction = replace(baseline, redemption_value_local=Decimal("101"))
    source_correction = replace(
        baseline,
        source=replace(
            baseline.source,
            fact_version=2,
            source_revision="revision-18",
        ),
    )

    assert baseline.content_hash() != economics_correction.content_hash()
    assert baseline.content_hash() != source_correction.content_hash()


def test_source_facts_reject_invalid_windows_versions_and_nonfinite_amounts() -> None:
    with pytest.raises(ValueError, match="on or after"):
        _basis(valid_from=date(2026, 2, 1), valid_to=date(2026, 1, 31))
    with pytest.raises(TypeError, match="fact_version must be an integer"):
        _source(fact_version=True)
    with pytest.raises(ValueError, match="must be finite"):
        _basis(initial_clean_cost_local=Decimal("NaN"))
