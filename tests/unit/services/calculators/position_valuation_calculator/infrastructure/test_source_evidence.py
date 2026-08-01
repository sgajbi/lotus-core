"""Tests for durable valuation input evidence mapping."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import FxRate, Portfolio, PositionHistory
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    InstrumentValuationPolicyAssignment,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactStatus,
    ResolvedValuationPolicyAssignment,
    ValuationAuthorityScope,
    ValuationPolicyAssignmentStatus,
    resolve_valuation_policy_assignment,
)

from src.services.calculators.position_valuation_calculator.app.infrastructure import (
    build_authoritative_valuation_evidence,
)

pytestmark = pytest.mark.unit


def _assignment(
    policy_id: str = "UNIT_PRICE_MARKET_VALUE",
) -> ResolvedValuationPolicyAssignment:
    assignment = InstrumentValuationPolicyAssignment(
        tenant_id="TENANT-SG",
        legal_book_id="BOOK-SG",
        security_id="BOND-001",
        policy_id=policy_id,
        policy_version=1,
        valid_from=date(2026, 1, 1),
        valid_to=None,
        assignment_status=ValuationPolicyAssignmentStatus.ACTIVE,
        assignment_version=1,
        source_system="security-master",
        source_record_id="POLICY-BOND-001",
        source_revision="1",
        observed_at=datetime(2026, 7, 29, 8, tzinfo=UTC),
        assignment_reason="Approved quote convention",
    )
    return resolve_valuation_policy_assignment(
        [assignment],
        tenant_id="TENANT-SG",
        legal_book_id="BOOK-SG",
        security_id="BOND-001",
        valuation_date=date(2026, 7, 29),
    )


def _price_fact() -> MarketPriceSourceFact:
    return MarketPriceSourceFact(
        scope=ValuationAuthorityScope("TENANT-SG", "BOOK-SG", "BOND-001"),
        price_date=date(2026, 7, 29),
        price=Decimal("1013.5"),
        currency="USD",
        quote_basis=MarketPriceQuoteBasis.UNIT_PRICE,
        source_reference=FinancialSourceReference(
            source_system="market-data",
            source_record_id="PRICE-BOND-001",
            source_revision="3",
            source_content_hash="a" * 64,
            observed_at=datetime(2026, 7, 29, 9, tzinfo=UTC),
        ),
        fact_status=MarketPriceSourceFactStatus.ACTIVE,
        fact_version=3,
    )


def _position(*, updated_at: datetime | None = None) -> PositionHistory:
    return PositionHistory(
        id=11,
        portfolio_id="PORT-001",
        security_id="BOND-001",
        transaction_id="TXN-001",
        position_date=date(2026, 7, 29),
        epoch=2,
        quantity=Decimal("10"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
        updated_at=updated_at or datetime(2026, 7, 29, 9, 5, tzinfo=UTC),
    )


def _portfolio() -> Portfolio:
    return Portfolio(
        id=7,
        portfolio_id="PORT-001",
        tenant_id="TENANT-SG",
        legal_book_id="BOOK-SG",
        base_currency="SGD",
        updated_at=datetime(2026, 7, 29, 9, 10, tzinfo=UTC),
    )


def _fx_rate() -> FxRate:
    return FxRate(
        id=5,
        from_currency="USD",
        to_currency="SGD",
        rate_date=date(2026, 7, 29),
        rate=Decimal("1.35"),
        updated_at=datetime(2026, 7, 29, 9, 15, tzinfo=UTC),
    )


def test_evidence_binds_assignment_price_position_portfolio_and_fx_sources() -> None:
    evidence = build_authoritative_valuation_evidence(
        assignment=_assignment(),
        price_fact=_price_fact(),
        position=_position(),
        portfolio=_portfolio(),
        fx_rate=_fx_rate(),
    )

    assert evidence.policy_assignment.source_system == "security-master"
    assert evidence.source_value == _price_fact().source_reference
    assert evidence.signed_quantity is not None
    assert evidence.signed_quantity.source_record_id.endswith("TXN-001")
    assert evidence.reporting_currency.source_system == "lotus-core.portfolio"
    assert evidence.direct_source_to_reporting_fx_rate is not None
    assert evidence.direct_source_to_reporting_fx_rate.source_system == "lotus-core.fx-rate"


def test_evidence_hash_changes_when_position_input_changes() -> None:
    baseline = build_authoritative_valuation_evidence(
        assignment=_assignment(),
        price_fact=_price_fact(),
        position=_position(),
        portfolio=_portfolio(),
        fx_rate=None,
    )
    changed_position = _position()
    changed_position.quantity = Decimal("11")
    changed = build_authoritative_valuation_evidence(
        assignment=_assignment(),
        price_fact=_price_fact(),
        position=changed_position,
        portfolio=_portfolio(),
        fx_rate=None,
    )

    assert baseline.signed_quantity is not None
    assert changed.signed_quantity is not None
    assert (
        baseline.signed_quantity.source_content_hash != changed.signed_quantity.source_content_hash
    )


def test_evidence_rejects_unpersisted_or_naive_rows() -> None:
    unpersisted = _position()
    unpersisted.id = None
    with pytest.raises(ValueError, match="persisted row id"):
        build_authoritative_valuation_evidence(
            assignment=_assignment(),
            price_fact=_price_fact(),
            position=unpersisted,
            portfolio=_portfolio(),
            fx_rate=None,
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        build_authoritative_valuation_evidence(
            assignment=_assignment(),
            price_fact=_price_fact(),
            position=_position(updated_at=datetime(2026, 7, 29, 9, 5)),
            portfolio=_portfolio(),
            fx_rate=None,
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "expected_error", "message"),
    [
        ("updated_at", "2026-07-29T09:05:00Z", TypeError, "must be a datetime"),
        ("portfolio_id", None, TypeError, "must be a string"),
        ("portfolio_id", "   ", ValueError, "must be nonblank"),
    ],
)
def test_evidence_rejects_malformed_persisted_position_identity(
    field_name: str,
    invalid_value: object,
    expected_error: type[Exception],
    message: str,
) -> None:
    position = _position()
    setattr(position, field_name, invalid_value)

    with pytest.raises(expected_error, match=message):
        build_authoritative_valuation_evidence(
            assignment=_assignment(),
            price_fact=_price_fact(),
            position=position,
            portfolio=_portfolio(),
            fx_rate=None,
        )


def test_position_quantity_is_not_relabelled_as_face_amount() -> None:
    policy_id = "DIRTY_PERCENT_FACE_MARKET_VALUE"

    evidence = build_authoritative_valuation_evidence(
        assignment=_assignment(policy_id),
        price_fact=_price_fact(),
        position=_position(),
        portfolio=_portfolio(),
        fx_rate=None,
    )

    assert evidence.signed_quantity is not None
    assert evidence.signed_face_amount is None


def test_factor_policy_does_not_infer_face_amount_from_position_quantity() -> None:
    policy_id = "DIRTY_PERCENT_FACTOR_MARKET_VALUE"

    evidence = build_authoritative_valuation_evidence(
        assignment=_assignment(policy_id),
        price_fact=_price_fact(),
        position=_position(),
        portfolio=_portfolio(),
        fx_rate=None,
    )

    assert evidence.signed_face_amount is None
