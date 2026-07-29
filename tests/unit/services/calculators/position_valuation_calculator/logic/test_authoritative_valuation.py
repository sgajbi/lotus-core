"""Golden application tests for authoritative valuation execution."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactError,
    MarketPriceSourceFactStatus,
    PositionValuationEvidence,
    UnsupportedValuationError,
    ValuationAuthorityScope,
    canonical_content_hash,
    resolve_position_valuation_policy,
)

from src.services.calculators.position_valuation_calculator.app.logic import (
    AuthoritativeValuationRequest,
    calculate_authoritative_valuation,
)

pytestmark = pytest.mark.unit


def _source(record_id: str) -> FinancialSourceReference:
    return FinancialSourceReference(
        source_system="authoritative-valuation-test",
        source_record_id=record_id,
        source_revision="revision-1",
        source_content_hash=canonical_content_hash({"record_id": record_id}),
        observed_at=datetime(2026, 7, 29, 8, tzinfo=UTC),
    )


def _fact(quote_basis: MarketPriceQuoteBasis, price: str) -> MarketPriceSourceFact:
    return MarketPriceSourceFact(
        scope=ValuationAuthorityScope("TENANT-SG", "BOOK-SG", "BOND-001"),
        price_date=date(2026, 7, 29),
        price=Decimal(price),
        currency="USD",
        quote_basis=quote_basis,
        source_reference=_source("market-price"),
        fact_status=MarketPriceSourceFactStatus.ACTIVE,
        fact_version=1,
    )


def _evidence() -> PositionValuationEvidence:
    return PositionValuationEvidence(
        policy_assignment=_source("policy-assignment"),
        source_value=_source("market-price"),
        source_currency=_source("market-price"),
        reporting_currency=_source("portfolio"),
        signed_quantity=_source("position"),
        signed_face_amount=_source("face-amount"),
    )


def test_unit_price_collision_is_not_rescaled_from_cost_magnitude() -> None:
    result = calculate_authoritative_valuation(
        AuthoritativeValuationRequest(
            policy=resolve_position_valuation_policy("UNIT_PRICE_MARKET_VALUE", 1),
            price_fact=_fact(MarketPriceQuoteBasis.UNIT_PRICE, "99.25"),
            signed_quantity=Decimal("10"),
            cost_basis_reporting=Decimal("10000"),
            cost_basis_local=Decimal("10000"),
            reporting_currency="USD",
            evidence=_evidence(),
        )
    )

    assert result.market_value_local == Decimal("992.5000000000")
    assert result.unrealized_total_local == Decimal("-9007.5000000000")
    assert result.calculation_lineage.algorithm_id == "authoritative-position-snapshot-valuation"
    assert result.calculation_lineage.numeric_output_policy is not None


def test_snapshot_lineage_binds_cost_basis_and_complete_outputs() -> None:
    common = {
        "policy": resolve_position_valuation_policy("UNIT_PRICE_MARKET_VALUE", 1),
        "price_fact": _fact(MarketPriceQuoteBasis.UNIT_PRICE, "99.25"),
        "signed_quantity": Decimal("10"),
        "cost_basis_local": Decimal("10000"),
        "reporting_currency": "USD",
        "evidence": _evidence(),
    }

    first = calculate_authoritative_valuation(
        AuthoritativeValuationRequest(
            **common,
            cost_basis_reporting=Decimal("10000"),
        )
    )
    corrected = calculate_authoritative_valuation(
        AuthoritativeValuationRequest(
            **common,
            cost_basis_reporting=Decimal("9999"),
        )
    )

    assert first.calculation_lineage.input_content_hash != (
        corrected.calculation_lineage.input_content_hash
    )
    assert first.calculation_lineage.calculation_content_hash != (
        corrected.calculation_lineage.calculation_content_hash
    )
    assert first.calculation_lineage.output_content_hash != (
        corrected.calculation_lineage.output_content_hash
    )


def test_percent_of_principal_uses_explicit_face_amount_and_denominator() -> None:
    result = calculate_authoritative_valuation(
        AuthoritativeValuationRequest(
            policy=resolve_position_valuation_policy(
                "CLEAN_PERCENT_FACE_NO_PERIODIC_ACCRUAL",
                1,
            ),
            price_fact=_fact(
                MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_CLEAN,
                "99.25",
            ),
            signed_quantity=Decimal("1000"),
            signed_face_amount=Decimal("1000000"),
            cost_basis_reporting=Decimal("990000"),
            cost_basis_local=Decimal("990000"),
            reporting_currency="USD",
            evidence=_evidence(),
        )
    )

    assert result.market_value_local == Decimal("992500.0000000000")
    assert result.unrealized_total_local == Decimal("2500.0000000000")


def test_quote_basis_mismatch_fails_before_calculation() -> None:
    with pytest.raises(MarketPriceSourceFactError, match="does not match"):
        calculate_authoritative_valuation(
            AuthoritativeValuationRequest(
                policy=resolve_position_valuation_policy("UNIT_PRICE_MARKET_VALUE", 1),
                price_fact=_fact(
                    MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_CLEAN,
                    "99.25",
                ),
                signed_quantity=Decimal("10"),
                cost_basis_reporting=Decimal("10000"),
                cost_basis_local=Decimal("10000"),
                reporting_currency="USD",
                evidence=_evidence(),
            )
        )


def test_principal_policy_fails_closed_without_face_amount() -> None:
    with pytest.raises(UnsupportedValuationError, match="signed_face_amount"):
        calculate_authoritative_valuation(
            AuthoritativeValuationRequest(
                policy=resolve_position_valuation_policy(
                    "CLEAN_PERCENT_FACE_NO_PERIODIC_ACCRUAL",
                    1,
                ),
                price_fact=_fact(
                    MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_CLEAN,
                    "99.25",
                ),
                signed_quantity=Decimal("1000"),
                cost_basis_reporting=Decimal("990000"),
                cost_basis_local=Decimal("990000"),
                reporting_currency="USD",
                evidence=_evidence(),
            )
        )
