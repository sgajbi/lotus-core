from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.services.financial_reconciliation_service.app.repositories import (
    reconciliation_repository as reconciliation_repo,
)

pytestmark = pytest.mark.asyncio


class _AsyncContextManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.begin_nested = MagicMock(return_value=_AsyncContextManager())
    session.refresh.return_value = None
    return session


async def test_create_run_normalizes_sentinel_correlation(mock_db_session: AsyncMock):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    repository.get_run_by_dedupe_key = AsyncMock(return_value=None)

    run, created = await repository.create_run(
        reconciliation_type="transaction_cashflow",
        portfolio_id="P1",
        business_date=date(2025, 8, 10),
        epoch=1,
        requested_by="system",
        dedupe_key="dedupe-1",
        correlation_id="<not-set>",
        tolerance=Decimal("0.01"),
    )

    assert created is True
    assert run.correlation_id is None
    mock_db_session.add.assert_called_once_with(run)
    mock_db_session.refresh.assert_awaited_once_with(run)


async def test_create_run_uses_injected_run_id_suffix_provider(mock_db_session: AsyncMock):
    repository = reconciliation_repo.ReconciliationRepository(
        mock_db_session,
        run_id_suffix_provider=lambda: "deterministic-run-id",
    )
    repository.get_run_by_dedupe_key = AsyncMock(return_value=None)

    run, created = await repository.create_run(
        reconciliation_type="transaction_cashflow",
        portfolio_id="P1",
        business_date=date(2025, 8, 10),
        epoch=1,
        requested_by="system",
        dedupe_key=None,
        correlation_id="corr-1",
        tolerance=Decimal("0.01"),
    )

    assert created is True
    assert run.run_id == "recon-deterministic-run-id"


async def test_create_run_returns_existing_row_after_dedupe_integrity_race(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    existing_run = MagicMock(run_id="recon-existing")
    repository.get_run_by_dedupe_key = AsyncMock(side_effect=[None, existing_run])
    mock_db_session.flush.side_effect = IntegrityError("stmt", "params", Exception("duplicate"))

    run, created = await repository.create_run(
        reconciliation_type="transaction_cashflow",
        portfolio_id="P1",
        business_date=date(2025, 8, 10),
        epoch=1,
        requested_by="system",
        dedupe_key="dedupe-1",
        correlation_id="corr-1",
        tolerance=Decimal("0.01"),
    )

    assert run is existing_run
    assert created is False
    assert repository.get_run_by_dedupe_key.await_count == 2


async def test_fetch_latest_fx_rate_normalizes_currency_codes_and_uses_functional_index_predicates(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = result

    fx_rate = await repository.fetch_latest_fx_rate(
        from_currency=" eur ",
        to_currency=" usd ",
        business_date=date(2026, 5, 28),
    )

    assert fx_rate is None
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "upper(trim(fx_rates.from_currency)) = 'eur'" in compiled_query
    assert "upper(trim(fx_rates.to_currency)) = 'usd'" in compiled_query
    assert "fx_rates.rate_date <= '2026-05-28'" in compiled_query
    assert "order by fx_rates.rate_date desc" in compiled_query
    assert "limit 1" in compiled_query


async def test_list_findings_uses_index_aligned_order(mock_db_session: AsyncMock):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result

    findings = await repository.list_findings("recon-123")

    assert findings == []
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "financial_reconciliation_findings.run_id = 'recon-123'" in compiled_query
    assert (
        "ORDER BY financial_reconciliation_findings.severity ASC, "
        "financial_reconciliation_findings.finding_type ASC, "
        "financial_reconciliation_findings.id ASC"
    ) in compiled_query


async def test_list_runs_uses_index_aligned_deterministic_order(mock_db_session: AsyncMock):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result

    runs = await repository.list_runs(
        reconciliation_type="position_valuation",
        portfolio_id="P1",
        limit=10,
    )

    assert runs == []
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert (
        "financial_reconciliation_runs.reconciliation_type = 'position_valuation'" in compiled_query
    )
    assert "financial_reconciliation_runs.portfolio_id = 'P1'" in compiled_query
    assert (
        "ORDER BY financial_reconciliation_runs.started_at DESC, "
        "financial_reconciliation_runs.id DESC"
    ) in compiled_query
    assert "LIMIT 10" in compiled_query


async def test_fetch_transaction_cashflow_rows_uses_index_friendly_business_date_range(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.all.return_value = []
    mock_db_session.execute.return_value = result

    rows = await repository.fetch_transaction_cashflow_rows(
        portfolio_id="P1",
        business_date=date(2026, 5, 28),
    )

    assert rows == []
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.transaction_date >= '2026-05-28 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2026-05-29 00:00:00'" in compiled_query
    assert "date(transactions.transaction_date)" not in compiled_query.lower()


async def test_fetch_position_valuation_rows_uses_normalized_instrument_join(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.all.return_value = []
    mock_db_session.execute.return_value = result

    rows = await repository.fetch_position_valuation_rows(
        portfolio_id="P1",
        business_date=date(2026, 5, 28),
        epoch=4,
    )

    assert rows == []
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert (
        "JOIN instruments ON trim(instruments.security_id) = "
        "trim(daily_position_snapshots.security_id)"
    ) in compiled_query
    assert "daily_position_snapshots.portfolio_id = 'P1'" in compiled_query
    assert "daily_position_snapshots.date = '2026-05-28'" in compiled_query
    assert "daily_position_snapshots.epoch = 4" in compiled_query


async def test_fetch_authoritative_position_timeseries_rows_uses_normalized_instrument_join(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.all.return_value = []
    mock_db_session.execute.return_value = result

    rows = await repository.fetch_authoritative_position_timeseries_rows(
        portfolio_id="P1",
        business_date=date(2026, 5, 28),
        epoch=4,
    )

    assert rows == []
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert (
        "JOIN instruments ON trim(instruments.security_id) = trim(position_timeseries.security_id)"
        in compiled_query
    )
    assert "position_timeseries.portfolio_id = 'P1'" in compiled_query
    assert "position_timeseries.date <= '2026-05-28'" in compiled_query
    assert "position_timeseries.epoch <= 4" in compiled_query
    assert "ORDER BY position_timeseries.security_id ASC" in compiled_query
