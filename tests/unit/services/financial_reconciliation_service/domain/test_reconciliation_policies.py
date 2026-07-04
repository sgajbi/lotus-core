from datetime import date
from decimal import Decimal

from services.financial_reconciliation_service.app.domain.reconciliation_policies import (
    PositionValuationEvidence,
    build_reconciliation_summary,
    expected_market_value_local,
    position_valuation_reconciliation_findings,
    requires_authoritative_fx_rate,
)


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


def test_position_valuation_policy_respects_bond_percent_of_par_pricing() -> None:
    market_value = expected_market_value_local(
        quantity=Decimal("180"),
        market_price=Decimal("101.35"),
        cost_basis_local=Decimal("178704"),
        product_type="BOND",
    )
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

    assert market_value == Decimal("182430.0")
    assert findings == []


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
