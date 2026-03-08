from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.financial_reconciliation_service.app.dtos import ReconciliationRunRequest
from src.services.financial_reconciliation_service.app.services.reconciliation_service import (
    ReconciliationService,
)

pytestmark = pytest.mark.asyncio


async def test_run_transaction_cashflow_records_missing_cashflow_finding():
    run = SimpleNamespace(run_id="recon-1")
    transaction = SimpleNamespace(
        portfolio_id="PORT-1",
        security_id="SEC-1",
        transaction_id="TXN-1",
        transaction_date=datetime(2026, 3, 8, tzinfo=timezone.utc),
        transaction_type="BUY",
        cash_entry_mode="AUTO_GENERATE",
    )
    rule = SimpleNamespace(
        classification="EXTERNAL",
        timing="SETTLEMENT",
        is_position_flow=True,
        is_portfolio_flow=False,
    )
    repository = AsyncMock()
    repository.create_run.return_value = run
    repository.fetch_transaction_cashflow_rows.return_value = [(transaction, rule, None)]

    service = ReconciliationService(repository)
    result = await service.run_transaction_cashflow(
        request=ReconciliationRunRequest(portfolio_id="PORT-1", business_date=date(2026, 3, 8)),
        correlation_id="corr-1",
    )

    assert result is run
    findings = repository.add_findings.await_args.args[0]
    assert len(findings) == 1
    assert findings[0].finding_type == "missing_cashflow"
    summary = repository.mark_run_completed.await_args.kwargs["summary"]
    assert summary["passed"] is False
    assert summary["error_count"] == 1


async def test_run_position_valuation_records_both_core_arithmetic_failures():
    run = SimpleNamespace(run_id="recon-2")
    snapshot = SimpleNamespace(
        portfolio_id="PORT-2",
        security_id="SEC-2",
        date=date(2026, 3, 8),
        epoch=0,
        quantity=Decimal("10"),
        market_price=Decimal("11"),
        market_value_local=Decimal("100"),
        cost_basis_local=Decimal("90"),
        unrealized_gain_loss_local=Decimal("5"),
    )
    repository = AsyncMock()
    repository.create_run.return_value = run
    repository.fetch_position_valuation_rows.return_value = [snapshot]

    service = ReconciliationService(repository)
    await service.run_position_valuation(
        request=ReconciliationRunRequest(portfolio_id="PORT-2", business_date=date(2026, 3, 8)),
        correlation_id="corr-2",
    )

    findings = repository.add_findings.await_args.args[0]
    assert {finding.finding_type for finding in findings} == {
        "market_value_local_mismatch",
        "unrealized_gain_loss_local_mismatch",
    }
    summary = repository.mark_run_completed.await_args.kwargs["summary"]
    assert summary["finding_count"] == 2
