from datetime import date
from decimal import Decimal

import pytest

from src.services.financial_reconciliation_service.app.domain.reconciliation_policies import (
    DEFAULT_VALUE_TOLERANCE,
    PositionValuationEvidence,
    PositionValuationReceiptEvidence,
    build_reconciliation_summary,
    position_valuation_reconciliation_findings,
    requires_authoritative_fx_rate,
    resolve_value_tolerance,
)


def test_value_tolerance_defaults_only_when_override_is_omitted() -> None:
    assert resolve_value_tolerance(None) == DEFAULT_VALUE_TOLERANCE
    assert resolve_value_tolerance(Decimal("0")) == Decimal("0")


def test_position_valuation_policy_records_market_and_unrealized_mismatches() -> None:
    findings = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-2",
            security_id="SEC-2",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("10"),
            market_price=Decimal("11"),
            market_value_local=Decimal("100"),
            cost_basis_local=Decimal("90"),
            unrealized_gain_loss_local=Decimal("5"),
            product_type="EQUITY",
        ),
        tolerance=Decimal("0.0001"),
    )

    assert [finding.finding_type for finding in findings] == [
        "market_value_local_mismatch",
        "unrealized_gain_loss_local_mismatch",
    ]
    assert findings[0].expected_value == {"market_value_local": "110"}
    assert findings[0].observed_value == {"market_value_local": "100", "delta": "-10"}
    assert findings[1].expected_value == {"unrealized_gain_loss_local": "20"}
    assert findings[1].observed_value == {
        "unrealized_gain_loss_local": "5",
        "delta": "-15",
    }


def test_requires_authoritative_fx_rate_only_when_currency_pair_is_complete_and_different() -> None:
    assert requires_authoritative_fx_rate("EUR", "USD") is True
    assert requires_authoritative_fx_rate("USD", "USD") is False
    assert requires_authoritative_fx_rate("", "USD") is False
    assert requires_authoritative_fx_rate("EUR", "") is False


def test_unscoped_bond_reconciliation_fails_without_quote_authority() -> None:
    findings = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-BOND",
            security_id="BOND-1",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("180"),
            market_price=Decimal("101.35"),
            market_value_local=Decimal("182430"),
            cost_basis_local=Decimal("178704"),
            unrealized_gain_loss_local=Decimal("3726"),
            product_type="BOND",
        ),
        tolerance=Decimal("0.0001"),
    )

    assert [finding.finding_type for finding in findings] == ["missing_bond_quote_authority"]
    assert findings[0].expected_value == {"valuation_receipt_supportability": "SUPPORTED"}
    assert findings[0].observed_value == {"valuation_receipt_supportability": None}
    assert findings[0].detail == {
        "reason": "bond valuation requires explicit quote-convention authority"
    }


def test_legacy_unscoped_bond_receipt_does_not_authorize_quote_interpretation() -> None:
    findings = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-BOND",
            security_id="BOND-LEGACY",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("10"),
            market_price=Decimal("1013.5"),
            market_value_local=Decimal("10135"),
            cost_basis_local=Decimal("10000"),
            unrealized_gain_loss_local=Decimal("135"),
            product_type="BOND",
            valuation_receipt=PositionValuationReceiptEvidence(
                supportability="LEGACY_UNSCOPED",
                policy_id=None,
                policy_version=None,
                quote_basis=None,
                receipt_hash="e" * 64,
            ),
        ),
        tolerance=Decimal("0.0001"),
    )

    assert [finding.finding_type for finding in findings] == ["missing_bond_quote_authority"]
    assert findings[0].observed_value == {"valuation_receipt_supportability": "LEGACY_UNSCOPED"}


def test_authoritative_unit_price_receipt_bypasses_legacy_bond_heuristic() -> None:
    findings = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-BOND",
            security_id="BOND-UNIT",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("10"),
            market_price=Decimal("100"),
            market_value_local=Decimal("1000"),
            cost_basis_local=Decimal("10000"),
            unrealized_gain_loss_local=Decimal("-9000"),
            product_type="BOND",
            valuation_receipt=PositionValuationReceiptEvidence(
                supportability="SUPPORTED",
                policy_id="UNIT_PRICE_MARKET_VALUE",
                policy_version=1,
                quote_basis="UNIT_PRICE",
                receipt_hash="a" * 64,
            ),
        ),
        tolerance=Decimal("0.0001"),
    )

    assert findings == []


@pytest.mark.parametrize(
    ("policy_id", "quote_basis"),
    [
        ("DIRTY_PERCENT_FACE_MARKET_VALUE", "PERCENT_OF_PRINCIPAL_DIRTY"),
        (
            "CLEAN_PERCENT_FACE_NO_PERIODIC_ACCRUAL",
            "PERCENT_OF_PRINCIPAL_CLEAN",
        ),
    ],
)
def test_authoritative_face_principal_receipt_fails_closed_without_authoritative_principal(
    policy_id: str,
    quote_basis: str,
) -> None:
    findings = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-BOND",
            security_id="BOND-FACE",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("1000000"),
            market_price=Decimal("99.25"),
            market_value_local=Decimal("992500"),
            cost_basis_local=Decimal("990000"),
            unrealized_gain_loss_local=Decimal("2500"),
            product_type="BOND",
            valuation_receipt=PositionValuationReceiptEvidence(
                supportability="SUPPORTED",
                policy_id=policy_id,
                policy_version=1,
                quote_basis=quote_basis,
                receipt_hash="c" * 64,
            ),
        ),
        tolerance=Decimal("0.0001"),
    )

    assert [finding.finding_type for finding in findings] == [
        "unsupported_authoritative_valuation_receipt"
    ]


def test_face_principal_receipt_with_unavailable_accrual_fails_closed() -> None:
    findings = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-BOND",
            security_id="BOND-ACCRUAL",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("1000000"),
            market_price=Decimal("99.25"),
            market_value_local=Decimal("992500"),
            cost_basis_local=Decimal("990000"),
            unrealized_gain_loss_local=Decimal("2500"),
            product_type="BOND",
            valuation_receipt=PositionValuationReceiptEvidence(
                supportability="SUPPORTED",
                policy_id="CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL",
                policy_version=1,
                quote_basis="PERCENT_OF_PRINCIPAL_CLEAN",
                receipt_hash="d" * 64,
            ),
        ),
        tolerance=Decimal("0.0001"),
    )

    assert [finding.finding_type for finding in findings] == [
        "unsupported_authoritative_valuation_receipt"
    ]


def test_invalid_authoritative_receipt_fails_closed_without_legacy_heuristic() -> None:
    findings = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-BOND",
            security_id="BOND-UNSUPPORTED",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("10"),
            market_price=Decimal("100"),
            market_value_local=Decimal("10000"),
            cost_basis_local=Decimal("10000"),
            unrealized_gain_loss_local=Decimal("0"),
            product_type="BOND",
            valuation_receipt=PositionValuationReceiptEvidence(
                supportability="SUPPORTED",
                policy_id="UNIT_PRICE_MARKET_VALUE",
                policy_version=1,
                quote_basis="PERCENT_OF_PRINCIPAL_CLEAN",
                receipt_hash="b" * 64,
            ),
        ),
        tolerance=Decimal("0.0001"),
    )

    assert [finding.finding_type for finding in findings] == [
        "unsupported_authoritative_valuation_receipt"
    ]
    assert findings[0].detail == {"receipt_hash": "b" * 64}


def test_position_valuation_policy_records_invalid_market_price_without_derived_math() -> None:
    findings = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-INVALID-PRICE",
            security_id="SEC-INVALID-PRICE",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("10"),
            market_price=Decimal("-12.50"),
            market_value_local=Decimal("-125"),
            cost_basis_local=Decimal("100"),
            unrealized_gain_loss_local=Decimal("-225"),
            product_type="EQUITY",
        ),
        tolerance=Decimal("0.0001"),
    )

    assert len(findings) == 1
    assert findings[0].finding_type == "invalid_market_price"
    assert findings[0].expected_value == {"market_price": ">0"}
    assert findings[0].observed_value == {"market_price": "-12.50"}
    assert findings[0].detail == {"quantity": "10", "product_type": "EQUITY"}


def test_reconciliation_summary_value_object_counts_error_and_warning_findings() -> None:
    error_finding = position_valuation_reconciliation_findings(
        evidence=PositionValuationEvidence(
            portfolio_id="PORT-2",
            security_id="SEC-2",
            business_date=date(2026, 3, 8),
            epoch=0,
            quantity=Decimal("10"),
            market_price=Decimal("-1"),
            market_value_local=Decimal("100"),
            cost_basis_local=Decimal("90"),
            unrealized_gain_loss_local=Decimal("5"),
            product_type="EQUITY",
        ),
        tolerance=Decimal("0.0001"),
    )[0]

    summary = build_reconciliation_summary(examined=3, findings=[error_finding])

    assert summary.as_dict() == {
        "examined_count": 3,
        "finding_count": 1,
        "error_count": 1,
        "warning_count": 0,
        "passed": False,
    }
