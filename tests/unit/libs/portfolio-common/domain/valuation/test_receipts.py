"""Tests for deterministic durable valuation calculation receipts."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactStatus,
    ValuationAuthorityScope,
    ValuationCalculationReceipt,
    ValuationReceiptSupportability,
    ValuationSnapshotIdentity,
    build_authoritative_valuation_receipt,
    build_calculation_lineage,
    build_legacy_valuation_receipt,
    canonical_content_hash,
)
from portfolio_common.domain.valuation.numeric_policy import (
    POSITION_VALUATION_LEDGER_OUTPUT_V1,
)


def _source(record_id: str) -> FinancialSourceReference:
    return FinancialSourceReference(
        source_system="valuation-receipt-test",
        source_record_id=record_id,
        source_revision="1",
        source_content_hash=canonical_content_hash({"record_id": record_id}),
        observed_at=datetime(2026, 7, 29, 10, tzinfo=UTC),
    )


def _identity() -> ValuationSnapshotIdentity:
    return ValuationSnapshotIdentity(
        portfolio_id="PORT-001",
        security_id="BOND-001",
        valuation_date=date(2026, 7, 29),
        epoch=2,
    )


def _price_fact(*, price: Decimal = Decimal("99.25")) -> MarketPriceSourceFact:
    return MarketPriceSourceFact(
        scope=ValuationAuthorityScope("TENANT-SG", "BOOK-SG", "BOND-001"),
        price_date=date(2026, 7, 29),
        price=price,
        currency="USD",
        quote_basis=MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        source_reference=_source("market-price"),
        fact_status=MarketPriceSourceFactStatus.ACTIVE,
        fact_version=3,
    )


def _lineage():
    return build_calculation_lineage(
        algorithm_id="POSITION_VALUATION_SCALING",
        algorithm_version=2,
        intermediate_precision=64,
        input_payload={"price": Decimal("99.25")},
        output_payload={"market_value": Decimal("992500")},
    )


def _legacy_lineage():
    return build_calculation_lineage(
        algorithm_id="legacy-unscoped-position-valuation",
        algorithm_version=1,
        intermediate_precision=64,
        input_payload={"price": Decimal("99.25")},
        output_payload={"market_value": Decimal("992500")},
        numeric_output_policy=POSITION_VALUATION_LEDGER_OUTPUT_V1.lineage_identity(),
    )


def _authoritative_receipt(
    *,
    price_fact: MarketPriceSourceFact | None = None,
) -> ValuationCalculationReceipt:
    return build_authoritative_valuation_receipt(
        snapshot_identity=_identity(),
        policy_id="CLEAN_PERCENT_FACE_NO_PERIODIC_ACCRUAL",
        policy_version=1,
        assignment_version=4,
        assignment_content_hash="b" * 64,
        policy_assignment_source=_source("policy-assignment"),
        price_fact=price_fact or _price_fact(),
        calculation_lineage=_lineage(),
    )


def test_authoritative_receipt_preserves_complete_policy_source_and_calculation_identity() -> None:
    receipt = _authoritative_receipt()

    assert receipt.supportability is ValuationReceiptSupportability.SUPPORTED
    assert receipt.policy_id == "CLEAN_PERCENT_FACE_NO_PERIODIC_ACCRUAL"
    assert receipt.assignment_version == 4
    assert receipt.quote_basis is MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_CLEAN
    assert receipt.price_fact_version == 3
    assert receipt.calculation_lineage == _lineage()
    assert receipt.receipt_hash == _authoritative_receipt().receipt_hash


def test_authoritative_receipt_hash_changes_when_price_fact_changes() -> None:
    assert (
        _authoritative_receipt().receipt_hash
        != _authoritative_receipt(price_fact=_price_fact(price=Decimal("99.50"))).receipt_hash
    )


def test_legacy_receipt_cannot_claim_authoritative_evidence() -> None:
    receipt = build_legacy_valuation_receipt(snapshot_identity=_identity())

    assert receipt.supportability is ValuationReceiptSupportability.LEGACY_UNSCOPED
    assert receipt.policy_id is None
    assert receipt.market_price_source is None
    assert receipt.calculation_lineage is None

    with pytest.raises(ValueError, match="cannot claim authoritative"):
        replace(receipt, policy_id="UNIT_PRICE_MARKET_VALUE")


def test_legacy_receipt_preserves_calculation_lineage_without_claiming_source_authority() -> None:
    receipt = build_legacy_valuation_receipt(
        snapshot_identity=_identity(),
        calculation_lineage=_legacy_lineage(),
    )

    assert receipt.supportability is ValuationReceiptSupportability.LEGACY_UNSCOPED
    assert receipt.policy_id is None
    assert receipt.market_price_source is None
    assert receipt.calculation_lineage == _legacy_lineage()

    with pytest.raises(ValueError, match="numeric output policy"):
        build_legacy_valuation_receipt(
            snapshot_identity=_identity(),
            calculation_lineage=_lineage(),
        )


def test_receipt_rejects_tampered_hash_and_duplicate_reasons() -> None:
    receipt = _authoritative_receipt()

    with pytest.raises(ValueError, match="does not match"):
        replace(receipt, receipt_hash="c" * 64)

    with pytest.raises(ValueError, match="unique nonblank"):
        replace(
            receipt,
            supportability_reasons=(
                "EXACT_POLICY_AND_PRICE_AUTHORITY",
                "EXACT_POLICY_AND_PRICE_AUTHORITY",
            ),
        )


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("portfolio_id", " ", ValueError),
        ("security_id", 7, TypeError),
        ("valuation_date", datetime(2026, 7, 29, tzinfo=UTC), TypeError),
        ("epoch", -1, ValueError),
    ],
)
def test_snapshot_identity_rejects_ambiguous_or_invalid_dimensions(
    field_name: str,
    value: object,
    error: type[Exception],
) -> None:
    values: dict[str, object] = {
        "portfolio_id": "PORT-001",
        "security_id": "BOND-001",
        "valuation_date": date(2026, 7, 29),
        "epoch": 2,
    }
    values[field_name] = value

    with pytest.raises(error):
        ValuationSnapshotIdentity(**values)  # type: ignore[arg-type]
