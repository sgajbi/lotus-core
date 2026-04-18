from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
    with patch(
        "src.services.financial_reconciliation_service.app.services.reconciliation_service.observe_financial_reconciliation_run"
    ) as observe_metric:
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
    observe_metric.assert_called_once()
    assert observe_metric.call_args.args[:2] == ("transaction_cashflow", "COMPLETED")


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
    with patch(
        "src.services.financial_reconciliation_service.app.services.reconciliation_service.observe_financial_reconciliation_run"
    ) as observe_metric:
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
    observe_metric.assert_called_once()
    assert observe_metric.call_args.args[:2] == ("position_valuation", "COMPLETED")


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


@pytest.mark.asyncio
async def test_run_timeseries_integrity_records_missing_portfolio_timeseries():
    run = SimpleNamespace(run_id="recon-ts-1")
    aggregate_row = SimpleNamespace(
        portfolio_id="PORT-TS-1",
        date=date(2026, 3, 8),
        epoch=2,
        position_row_count=3,
        bod_market_value=Decimal("100"),
        bod_cashflow=Decimal("10"),
        eod_cashflow=Decimal("5"),
        eod_market_value=Decimal("115"),
        fees=Decimal("1"),
    )
    repository = AsyncMock()
    repository.create_run.return_value = (run, True)
    repository.fetch_portfolio_timeseries_rows.return_value = []
    repository.fetch_position_timeseries_aggregates.return_value = [aggregate_row]
    repository.fetch_snapshot_counts.return_value = []

    service = ReconciliationService(repository)
    with patch(
        "src.services.financial_reconciliation_service.app.services.reconciliation_service.observe_financial_reconciliation_run"
    ) as observe_metric:
        await service.run_timeseries_integrity(
            request=ReconciliationRunRequest(portfolio_id="PORT-TS-1", business_date=date(2026, 3, 8), epoch=2),
            correlation_id="corr-ts-1",
        )

    findings = repository.add_findings.await_args.args[0]
    assert len(findings) == 1
    assert findings[0].finding_type == "missing_portfolio_timeseries"
    summary = repository.mark_run_completed.await_args.kwargs["summary"]
    assert summary["error_count"] == 1
    observe_metric.assert_called_once()
    assert observe_metric.call_args.args[:2] == ("timeseries_integrity", "COMPLETED")


@pytest.mark.asyncio
async def test_run_timeseries_integrity_records_completeness_and_aggregate_mismatches():
    run = SimpleNamespace(run_id="recon-ts-2")
    portfolio_row = SimpleNamespace(
        portfolio_id="PORT-TS-2",
        date=date(2026, 3, 8),
        epoch=4,
        bod_market_value=Decimal("200"),
        bod_cashflow=Decimal("20"),
        eod_cashflow=Decimal("15"),
        eod_market_value=Decimal("230"),
        fees=Decimal("3"),
    )
    aggregate_row = SimpleNamespace(
        portfolio_id="PORT-TS-2",
        date=date(2026, 3, 8),
        epoch=4,
        position_row_count=1,
        bod_market_value=Decimal("190"),
        bod_cashflow=Decimal("20"),
        eod_cashflow=Decimal("10"),
        eod_market_value=Decimal("225"),
        fees=Decimal("1"),
    )
    snapshot_count_row = SimpleNamespace(
        portfolio_id="PORT-TS-2",
        date=date(2026, 3, 8),
        epoch=4,
        snapshot_count=3,
    )
    repository = AsyncMock()
    repository.create_run.return_value = (run, True)
    repository.fetch_portfolio_timeseries_rows.return_value = [portfolio_row]
    repository.fetch_position_timeseries_aggregates.return_value = [aggregate_row]
    repository.fetch_snapshot_counts.return_value = [snapshot_count_row]

    service = ReconciliationService(repository)
    await service.run_timeseries_integrity(
        request=ReconciliationRunRequest(portfolio_id="PORT-TS-2", business_date=date(2026, 3, 8), epoch=4),
        correlation_id="corr-ts-2",
    )

    findings = repository.add_findings.await_args.args[0]
    assert {finding.finding_type for finding in findings} == {
        "position_timeseries_completeness_gap",
        "portfolio_timeseries_aggregate_mismatch",
    }
    mismatch_finding = next(
        finding for finding in findings if finding.finding_type == "portfolio_timeseries_aggregate_mismatch"
    )
    assert mismatch_finding.detail["bod_market_value"]["delta"] == "10"
    assert mismatch_finding.detail["eod_cashflow"]["delta"] == "5"
    assert mismatch_finding.detail["fees"]["delta"] == "2"
    summary = repository.mark_run_completed.await_args.kwargs["summary"]
    assert summary["finding_count"] == 2
    assert summary["passed"] is False
