from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import AsyncMock, patch

import pytest

from src.services.financial_reconciliation_service.app.dtos import ReconciliationRunRequest
from src.services.financial_reconciliation_service.app.ports.reconciliation_repository_ports import (
    ReconciliationRepositoryPort,
)
from src.services.financial_reconciliation_service.app.services.reconciliation_service import (
    ReconciliationService,
)


class FakeMonotonicTimer:
    def __init__(self, readings: list[float]):
        self._readings = list(readings)

    def seconds(self) -> float:
        return self._readings.pop(0)


class FakeIdGenerator:
    def __init__(self, ids: list[str]):
        self._ids = list(ids)

    def new_id(self) -> str:
        return self.new_hex()

    def new_hex(self) -> str:
        return self._ids.pop(0)


def test_reconciliation_service_depends_on_repository_port() -> None:
    hints = get_type_hints(ReconciliationService.__init__)

    assert hints["repository"] is ReconciliationRepositoryPort


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
async def test_run_transaction_cashflow_uses_injected_timer_and_id_generator():
    run = SimpleNamespace(run_id="recon-deterministic")
    transaction = SimpleNamespace(
        portfolio_id="PORT-DETERMINISTIC",
        security_id="SEC-DETERMINISTIC",
        transaction_id="TXN-DETERMINISTIC",
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

    service = ReconciliationService(
        repository,
        monotonic_timer=FakeMonotonicTimer([100.25, 103.75]),
        id_generator=FakeIdGenerator(["abc123"]),
    )
    with patch(
        "src.services.financial_reconciliation_service.app.services.reconciliation_service.observe_financial_reconciliation_run"
    ) as observe_metric:
        await service.run_transaction_cashflow(
            request=ReconciliationRunRequest(
                portfolio_id="PORT-DETERMINISTIC",
                business_date=date(2026, 3, 8),
            ),
            correlation_id="corr-deterministic",
        )

    findings = repository.add_findings.await_args.args[0]
    assert findings[0].finding_id == "finding-abc123"
    assert observe_metric.call_args.args[2] == 3.5


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
        cost_basis=Decimal("90"),
        market_value_local=Decimal("100"),
        cost_basis_local=Decimal("90"),
        unrealized_gain_loss_local=Decimal("5"),
    )
    instrument = SimpleNamespace(currency="USD", product_type="EQUITY")
    portfolio = SimpleNamespace(base_currency="USD")
    repository = AsyncMock()
    repository.create_run.return_value = (run, True)
    repository.fetch_position_valuation_rows.return_value = [(snapshot, instrument, portfolio)]

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
async def test_run_position_valuation_respects_bond_percent_of_par_pricing():
    run = SimpleNamespace(run_id="recon-bond")
    snapshot = SimpleNamespace(
        portfolio_id="PORT-BOND",
        security_id="BOND-1",
        date=date(2026, 3, 8),
        epoch=0,
        quantity=Decimal("180"),
        market_price=Decimal("101.35"),
        market_value_local=Decimal("182430"),
        cost_basis=Decimal("178704"),
        cost_basis_local=Decimal("178704"),
        unrealized_gain_loss_local=Decimal("3726"),
    )
    instrument = SimpleNamespace(currency="USD", product_type="BOND")
    portfolio = SimpleNamespace(base_currency="USD")
    repository = AsyncMock()
    repository.create_run.return_value = (run, True)
    repository.fetch_position_valuation_rows.return_value = [(snapshot, instrument, portfolio)]

    service = ReconciliationService(repository)
    with patch(
        "src.services.financial_reconciliation_service.app.services.reconciliation_service.observe_financial_reconciliation_run"
    ):
        await service.run_position_valuation(
            request=ReconciliationRunRequest(
                portfolio_id="PORT-BOND", business_date=date(2026, 3, 8)
            ),
            correlation_id="corr-bond",
        )

    findings = repository.add_findings.await_args.args[0]
    assert findings == []
    summary = repository.mark_run_completed.await_args.kwargs["summary"]
    assert summary["finding_count"] == 0


@pytest.mark.asyncio
async def test_run_position_valuation_normalizes_string_amounts():
    run = SimpleNamespace(run_id="recon-string-amounts")
    snapshot = SimpleNamespace(
        portfolio_id="PORT-STR",
        security_id="SEC-STR",
        date=date(2026, 3, 8),
        epoch=0,
        quantity="10",
        market_price="11",
        market_value_local="110",
        cost_basis="90",
        cost_basis_local="90",
        unrealized_gain_loss_local="20",
    )
    instrument = SimpleNamespace(currency="USD", product_type="EQUITY")
    portfolio = SimpleNamespace(base_currency="USD")
    repository = AsyncMock()
    repository.create_run.return_value = (run, True)
    repository.fetch_position_valuation_rows.return_value = [(snapshot, instrument, portfolio)]

    service = ReconciliationService(repository)
    await service.run_position_valuation(
        request=ReconciliationRunRequest(portfolio_id="PORT-STR", business_date=date(2026, 3, 8)),
        correlation_id="corr-string-amounts",
    )

    assert repository.add_findings.await_args.args[0] == []
    summary = repository.mark_run_completed.await_args.kwargs["summary"]
    assert summary["examined_count"] == 1
    assert summary["finding_count"] == 0
    assert summary["passed"] is True


@pytest.mark.asyncio
async def test_run_position_valuation_records_invalid_market_price_without_derived_math():
    run = SimpleNamespace(run_id="recon-invalid-price")
    snapshot = SimpleNamespace(
        portfolio_id="PORT-INVALID-PRICE",
        security_id="SEC-INVALID-PRICE",
        date=date(2026, 3, 8),
        epoch=0,
        quantity=Decimal("10"),
        market_price=Decimal("-12.50"),
        market_value_local=Decimal("-125"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
        unrealized_gain_loss_local=Decimal("-225"),
    )
    instrument = SimpleNamespace(currency="USD", product_type="EQUITY")
    portfolio = SimpleNamespace(base_currency="USD")
    repository = AsyncMock()
    repository.create_run.return_value = (run, True)
    repository.fetch_position_valuation_rows.return_value = [(snapshot, instrument, portfolio)]

    service = ReconciliationService(repository)
    await service.run_position_valuation(
        request=ReconciliationRunRequest(
            portfolio_id="PORT-INVALID-PRICE", business_date=date(2026, 3, 8)
        ),
        correlation_id="corr-invalid-price",
    )

    findings = repository.add_findings.await_args.args[0]
    assert len(findings) == 1
    assert findings[0].finding_type == "invalid_market_price"
    assert findings[0].expected_value == {"market_price": ">0"}
    assert findings[0].observed_value == {"market_price": "-12.50"}
    summary = repository.mark_run_completed.await_args.kwargs["summary"]
    assert summary["examined_count"] == 1
    assert summary["finding_count"] == 1
    assert summary["error_count"] == 1
    assert summary["passed"] is False


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
    repository.fetch_authoritative_position_timeseries_rows.return_value = []
    repository.fetch_authoritative_snapshot_count.return_value = 0

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
    repository.fetch_authoritative_position_timeseries_rows.return_value = []
    repository.fetch_authoritative_snapshot_count.return_value = 0

    service = ReconciliationService(repository)
    with patch(
        "src.services.financial_reconciliation_service.app.services.reconciliation_service.observe_financial_reconciliation_run"
    ) as observe_metric:
        await service.run_timeseries_integrity(
            request=ReconciliationRunRequest(
                portfolio_id="PORT-TS-1", business_date=date(2026, 3, 8), epoch=2
            ),
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
        bod_market_value="200",
        bod_cashflow="20",
        eod_cashflow="15",
        eod_market_value="230",
        fees="3",
    )
    authoritative_position_row = SimpleNamespace(
        portfolio_id="PORT-TS-2",
        security_id="SEC-TS-2",
        date=date(2026, 3, 8),
        epoch=4,
        bod_market_value="190",
        bod_cashflow_portfolio="20",
        eod_cashflow_portfolio="10",
        eod_market_value="225",
        fees="1",
    )
    instrument = SimpleNamespace(currency="USD")
    owning_portfolio = SimpleNamespace(base_currency="USD")
    repository = AsyncMock()
    repository.create_run.return_value = (run, True)
    repository.fetch_portfolio_timeseries_rows.return_value = [portfolio_row]
    repository.fetch_position_timeseries_aggregates.return_value = []
    repository.fetch_snapshot_counts.return_value = []
    repository.fetch_authoritative_position_timeseries_rows.return_value = [
        (authoritative_position_row, instrument, owning_portfolio)
    ]
    repository.fetch_authoritative_snapshot_count.return_value = 3

    service = ReconciliationService(repository)
    await service.run_timeseries_integrity(
        request=ReconciliationRunRequest(
            portfolio_id="PORT-TS-2", business_date=date(2026, 3, 8), epoch=4
        ),
        correlation_id="corr-ts-2",
    )

    findings = repository.add_findings.await_args.args[0]
    assert {finding.finding_type for finding in findings} == {
        "position_timeseries_completeness_gap",
        "portfolio_timeseries_aggregate_mismatch",
    }
    mismatch_finding = next(
        finding
        for finding in findings
        if finding.finding_type == "portfolio_timeseries_aggregate_mismatch"
    )
    assert mismatch_finding.detail["bod_market_value"]["delta"] == "10"
    assert mismatch_finding.detail["eod_cashflow"]["delta"] == "5"
    assert mismatch_finding.detail["fees"]["delta"] == "2"
    summary = repository.mark_run_completed.await_args.kwargs["summary"]
    assert summary["finding_count"] == 2
    assert summary["passed"] is False


@pytest.mark.asyncio
async def test_authoritative_portfolio_metrics_skip_non_positive_fx_rates():
    position_row = SimpleNamespace(
        date=date(2026, 3, 8),
        bod_market_value=Decimal("100"),
        bod_cashflow_portfolio=Decimal("5"),
        eod_cashflow_portfolio=Decimal("7"),
        eod_market_value=Decimal("120"),
        fees=Decimal("1"),
    )
    instrument = SimpleNamespace(currency="EUR")
    portfolio = SimpleNamespace(base_currency="USD")
    repository = AsyncMock()
    repository.fetch_authoritative_position_timeseries_rows.return_value = [
        (position_row, instrument, portfolio)
    ]
    repository.fetch_latest_fx_rate.return_value = SimpleNamespace(rate=Decimal("-1.08"))

    service = ReconciliationService(repository)
    metrics, row_count = await service._aggregate_authoritative_portfolio_metrics(
        portfolio_id="PORT-TS-FX",
        business_date=date(2026, 3, 8),
        epoch=1,
    )

    assert row_count == 1
    assert metrics == {
        "bod_market_value": Decimal("0"),
        "bod_cashflow": Decimal("0"),
        "eod_cashflow": Decimal("0"),
        "eod_market_value": Decimal("0"),
        "fees": Decimal("0"),
    }


@pytest.mark.asyncio
async def test_authoritative_portfolio_metrics_zero_default_sparse_amounts():
    position_row = SimpleNamespace(
        date=date(2026, 3, 8),
        bod_market_value="100",
        bod_cashflow_portfolio=" ",
        eod_cashflow_portfolio=None,
        eod_market_value="120.5",
        fees="",
    )
    instrument = SimpleNamespace(currency="USD")
    portfolio = SimpleNamespace(base_currency="USD")
    repository = AsyncMock()
    repository.fetch_authoritative_position_timeseries_rows.return_value = [
        (position_row, instrument, portfolio)
    ]

    service = ReconciliationService(repository)
    metrics, row_count = await service._aggregate_authoritative_portfolio_metrics(
        portfolio_id="PORT-TS-SPARSE",
        business_date=date(2026, 3, 8),
        epoch=1,
    )

    assert row_count == 1
    assert metrics == {
        "bod_market_value": Decimal("100"),
        "bod_cashflow": Decimal("0"),
        "eod_cashflow": Decimal("0"),
        "eod_market_value": Decimal("120.5"),
        "fees": Decimal("0"),
    }
    repository.fetch_latest_fx_rate.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_timeseries_integrity_uses_authoritative_asof_rows_when_portfolio_row_exists():
    run = SimpleNamespace(run_id="recon-ts-3")
    portfolio_row = SimpleNamespace(
        portfolio_id="PORT-TS-3",
        date=date(2026, 3, 8),
        epoch=13,
        bod_market_value=Decimal("130"),
        bod_cashflow=Decimal("0"),
        eod_cashflow=Decimal("-18"),
        eod_market_value=Decimal("112"),
        fees=Decimal("0"),
    )
    stale_exact_epoch_aggregate = SimpleNamespace(
        portfolio_id="PORT-TS-3",
        date=date(2026, 3, 8),
        epoch=3,
        position_row_count=2,
        bod_market_value=Decimal("10"),
        bod_cashflow=Decimal("0"),
        eod_cashflow=Decimal("-36"),
        eod_market_value=Decimal("8"),
        fees=Decimal("0"),
    )
    authoritative_rows = [
        (
            SimpleNamespace(
                portfolio_id="PORT-TS-3",
                security_id="SEC-USD",
                date=date(2026, 3, 8),
                epoch=0,
                bod_market_value=Decimal("100"),
                bod_cashflow_portfolio=Decimal("0"),
                eod_cashflow_portfolio=Decimal("0"),
                eod_market_value=Decimal("100"),
                fees=Decimal("0"),
            ),
            SimpleNamespace(currency="USD"),
            SimpleNamespace(base_currency="USD"),
        ),
        (
            SimpleNamespace(
                portfolio_id="PORT-TS-3",
                security_id="SEC-EUR",
                date=date(2026, 3, 7),
                epoch=1,
                bod_market_value=Decimal("25"),
                bod_cashflow_portfolio=Decimal("0"),
                eod_cashflow_portfolio=Decimal("-15"),
                eod_market_value=Decimal("10"),
                fees=Decimal("0"),
            ),
            SimpleNamespace(currency="EUR"),
            SimpleNamespace(base_currency="USD"),
        ),
    ]
    repository = AsyncMock()
    repository.create_run.return_value = (run, True)
    repository.fetch_portfolio_timeseries_rows.return_value = [portfolio_row]
    repository.fetch_position_timeseries_aggregates.return_value = [stale_exact_epoch_aggregate]
    repository.fetch_snapshot_counts.return_value = []
    repository.fetch_authoritative_position_timeseries_rows.return_value = authoritative_rows
    repository.fetch_authoritative_snapshot_count.return_value = 2
    repository.fetch_latest_fx_rate.return_value = SimpleNamespace(rate=Decimal("1.2"))

    service = ReconciliationService(repository)
    await service.run_timeseries_integrity(
        request=ReconciliationRunRequest(
            portfolio_id="PORT-TS-3",
            business_date=date(2026, 3, 8),
            epoch=13,
        ),
        correlation_id="corr-ts-3",
    )

    findings = repository.add_findings.await_args.args[0]
    assert findings == []
    repository.fetch_authoritative_position_timeseries_rows.assert_awaited_once_with(
        portfolio_id="PORT-TS-3",
        business_date=date(2026, 3, 8),
        epoch=13,
    )
    repository.fetch_latest_fx_rate.assert_awaited_once_with(
        from_currency="EUR",
        to_currency="USD",
        business_date=date(2026, 3, 7),
    )
