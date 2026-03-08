from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.financial_reconciliation_service.app.dtos import ReconciliationRunRequest
from src.services.financial_reconciliation_service.app.services.reconciliation_service import (
    ReconciliationService,
)


@pytest.mark.asyncio
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
    repository.create_run.return_value = (run, True)
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


@pytest.mark.asyncio
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
    repository.create_run.return_value = (run, True)
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


@pytest.mark.asyncio
async def test_run_automatic_bundle_applies_dedupe_for_system_pipeline():
    transaction_run = SimpleNamespace(run_id="recon-tx")
    valuation_run = SimpleNamespace(run_id="recon-val")
    timeseries_run = SimpleNamespace(run_id="recon-ts")
    repository = AsyncMock()
    repository.create_run.side_effect = [
        (transaction_run, True),
        (valuation_run, True),
        (timeseries_run, True),
    ]
    repository.fetch_transaction_cashflow_rows.return_value = []
    repository.fetch_position_valuation_rows.return_value = []
    repository.fetch_portfolio_timeseries_rows.return_value = []
    repository.fetch_position_timeseries_aggregates.return_value = []
    repository.fetch_snapshot_counts.return_value = []

    service = ReconciliationService(repository)
    result = await service.run_automatic_bundle(
        request=ReconciliationRunRequest(
            portfolio_id="PORT-AUTO",
            business_date=date(2026, 3, 8),
            epoch=4,
            requested_by="system_pipeline",
        ),
        correlation_id="corr-auto",
        reconciliation_types=[
            "transaction_cashflow",
            "position_valuation",
            "timeseries_integrity",
        ],
    )

    assert result == {
        "transaction_cashflow": transaction_run,
        "position_valuation": valuation_run,
        "timeseries_integrity": timeseries_run,
    }
    dedupe_keys = [call.kwargs["dedupe_key"] for call in repository.create_run.await_args_list]
    assert dedupe_keys == [
        "auto:transaction_cashflow:PORT-AUTO:2026-03-08:4",
        "auto:position_valuation:PORT-AUTO:2026-03-08:4",
        "auto:timeseries_integrity:PORT-AUTO:2026-03-08:4",
    ]


def test_determine_automatic_bundle_outcome_requires_replay_for_error_findings():
    runs = {
        "transaction_cashflow": SimpleNamespace(
            run_id="recon-tx",
            status="COMPLETED",
            summary={"error_count": 2, "warning_count": 1},
        ),
        "position_valuation": SimpleNamespace(
            run_id="recon-val",
            status="COMPLETED",
            summary={"error_count": 0, "warning_count": 0},
        ),
    }

    outcome = ReconciliationService.determine_automatic_bundle_outcome(runs)

    assert outcome.outcome_status == "REQUIRES_REPLAY"
    assert outcome.blocking_reconciliation_types == ["transaction_cashflow"]
    assert outcome.error_count == 2
    assert outcome.warning_count == 1


def test_determine_automatic_bundle_outcome_escalates_failed_runs():
    runs = {
        "transaction_cashflow": SimpleNamespace(
            run_id="recon-tx",
            status="FAILED",
            summary={"error_count": 0, "warning_count": 0},
        ),
        "timeseries_integrity": SimpleNamespace(
            run_id="recon-ts",
            status="COMPLETED",
            summary={"error_count": 1, "warning_count": 0},
        ),
    }

    outcome = ReconciliationService.determine_automatic_bundle_outcome(runs)

    assert outcome.outcome_status == "FAILED"
    assert outcome.blocking_reconciliation_types == [
        "timeseries_integrity",
        "transaction_cashflow",
    ]
    assert outcome.run_ids == {
        "transaction_cashflow": "recon-tx",
        "timeseries_integrity": "recon-ts",
    }
