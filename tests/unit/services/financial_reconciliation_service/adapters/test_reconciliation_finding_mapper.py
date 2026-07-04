from datetime import date

from services.financial_reconciliation_service.app.adapters.reconciliation_finding_mapper import (
    reconciliation_finding_to_orm,
)
from services.financial_reconciliation_service.app.domain.reconciliation_policies import (
    ReconciliationFinding,
)


def test_reconciliation_finding_mapper_preserves_domain_payload_fields() -> None:
    finding = ReconciliationFinding(
        reconciliation_type="position_valuation",
        finding_type="market_value_local_mismatch",
        severity="ERROR",
        portfolio_id="PORT-1",
        security_id="SEC-1",
        transaction_id=None,
        business_date=date(2026, 3, 8),
        epoch=4,
        expected_value={"market_value_local": "110"},
        observed_value={"market_value_local": "100", "delta": "-10"},
        detail={"product_type": "EQUITY"},
    )

    row = reconciliation_finding_to_orm(
        finding,
        run_id="recon-1",
        finding_id="finding-1",
    )

    assert row.finding_id == "finding-1"
    assert row.run_id == "recon-1"
    assert row.reconciliation_type == "position_valuation"
    assert row.finding_type == "market_value_local_mismatch"
    assert row.severity == "ERROR"
    assert row.portfolio_id == "PORT-1"
    assert row.security_id == "SEC-1"
    assert row.transaction_id is None
    assert row.business_date == date(2026, 3, 8)
    assert row.epoch == 4
    assert row.expected_value == {"market_value_local": "110"}
    assert row.observed_value == {"market_value_local": "100", "delta": "-10"}
    assert row.detail == {"product_type": "EQUITY"}
