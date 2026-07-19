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
    session.add_all = MagicMock()
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
        aggregation_revision=4,
        requested_by="system",
        dedupe_key="dedupe-1",
        correlation_id="<not-set>",
        tolerance=Decimal("0.01"),
    )

    assert created is True
    assert run.correlation_id is None
    assert run.aggregation_revision == 4
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
        aggregation_revision=None,
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
        aggregation_revision=4,
        requested_by="system",
        dedupe_key="dedupe-1",
        correlation_id="corr-1",
        tolerance=Decimal("0.01"),
    )

    assert run is existing_run
    assert created is False
    assert repository.get_run_by_dedupe_key.await_count == 2


async def test_create_run_returns_preexisting_deduplicated_run_without_writing(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    existing_run = MagicMock(run_id="recon-existing")
    repository.get_run_by_dedupe_key = AsyncMock(return_value=existing_run)

    run, created = await repository.create_run(
        reconciliation_type="transaction_cashflow",
        portfolio_id="P1",
        business_date=date(2025, 8, 10),
        epoch=1,
        aggregation_revision=4,
        requested_by="system",
        dedupe_key="dedupe-1",
        correlation_id="corr-1",
        tolerance=Decimal("0.01"),
    )

    assert run is existing_run
    assert created is False
    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_awaited()


@pytest.mark.parametrize("dedupe_key", [None, "dedupe-1"])
async def test_create_run_reraises_unresolved_integrity_error(
    mock_db_session: AsyncMock,
    dedupe_key: str | None,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    repository.get_run_by_dedupe_key = AsyncMock(return_value=None)
    error = IntegrityError("stmt", "params", Exception("constraint violation"))
    mock_db_session.flush.side_effect = error

    with pytest.raises(IntegrityError) as raised:
        await repository.create_run(
            reconciliation_type="transaction_cashflow",
            portfolio_id="P1",
            business_date=date(2025, 8, 10),
            epoch=1,
            aggregation_revision=4,
            requested_by="system",
            dedupe_key=dedupe_key,
            correlation_id="corr-1",
            tolerance=Decimal("0.01"),
        )

    assert raised.value is error
    assert repository.get_run_by_dedupe_key.await_count == (2 if dedupe_key else 0)


async def test_run_lookup_and_mutations_delegate_to_the_session(mock_db_session: AsyncMock):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    stored_run = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = stored_run
    mock_db_session.execute.return_value = result

    assert await repository.get_run_by_dedupe_key("dedupe-1") is stored_run
    dedupe_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "financial_reconciliation_runs.dedupe_key = 'dedupe-1'" in dedupe_query

    assert await repository.get_run("recon-1") is stored_run
    run_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "financial_reconciliation_runs.run_id = 'recon-1'" in run_query

    findings = [MagicMock(), MagicMock()]
    await repository.add_findings(findings)
    mock_db_session.add_all.assert_called_once_with(findings)

    await repository.mark_run_completed(
        stored_run,
        status="passed",
        summary={"matched": 2},
        failure_reason=None,
    )
    assert stored_run.status == "passed"
    assert stored_run.summary == {"matched": 2}
    assert stored_run.failure_reason is None
    assert stored_run.completed_at is not None
    assert mock_db_session.flush.await_count == 2
    mock_db_session.refresh.assert_awaited_once_with(stored_run)


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


async def test_list_runs_without_optional_filters(mock_db_session: AsyncMock):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result

    assert await repository.list_runs() == []
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "WHERE" not in compiled_query
    assert "LIMIT 50" in compiled_query


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


async def test_fetch_transaction_cashflow_rows_without_optional_filters(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.all.return_value = []
    mock_db_session.execute.return_value = result

    assert (
        await repository.fetch_transaction_cashflow_rows(
            portfolio_id=None,
            business_date=None,
        )
        == []
    )
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "WHERE" not in compiled_query


async def test_fetch_position_valuation_rows_selects_authoritative_rows_through_target_epoch(
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
    assert "daily_position_snapshots.epoch <= 4" in compiled_query
    assert "row_number() over" in compiled_query.lower()
    assert "partition by daily_position_snapshots.portfolio_id" in compiled_query.lower()
    assert "order by daily_position_snapshots.epoch desc" in compiled_query.lower()
    assert "anon_1.rn = 1" in compiled_query.lower()


@pytest.mark.parametrize(
    ("portfolio_id", "business_date", "epoch", "expected_predicates"),
    [
        ("P1", date(2026, 5, 28), None, ("portfolio_id = 'P1'", "date = '2026-05-28'")),
        ("P1", None, 4, ("portfolio_id = 'P1'", "epoch = 4")),
        (None, None, None, ()),
    ],
)
async def test_fetch_position_valuation_rows_supports_non_authoritative_filter_combinations(
    mock_db_session: AsyncMock,
    portfolio_id: str | None,
    business_date: date | None,
    epoch: int | None,
    expected_predicates: tuple[str, ...],
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.all.return_value = []
    mock_db_session.execute.return_value = result

    assert (
        await repository.fetch_position_valuation_rows(
            portfolio_id=portfolio_id,
            business_date=business_date,
            epoch=epoch,
        )
        == []
    )
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "row_number() over" not in compiled_query
    for predicate in expected_predicates:
        assert predicate.lower() in compiled_query


async def test_fetch_position_valuation_rows_ranks_all_portfolios_when_unscoped(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.all.return_value = []
    mock_db_session.execute.return_value = result

    assert (
        await repository.fetch_position_valuation_rows(
            portfolio_id=None,
            business_date=date(2026, 5, 28),
            epoch=4,
        )
        == []
    )
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "row_number() over" in compiled_query
    assert "daily_position_snapshots.date = '2026-05-28'" in compiled_query
    assert "daily_position_snapshots.epoch <= 4" in compiled_query


@pytest.mark.parametrize(
    "method_name",
    [
        "fetch_portfolio_timeseries_rows",
        "fetch_position_timeseries_aggregates",
        "fetch_snapshot_counts",
    ],
)
@pytest.mark.parametrize("with_filters", [False, True])
async def test_repository_aggregate_queries_cover_optional_filter_paths(
    mock_db_session: AsyncMock,
    method_name: str,
    with_filters: bool,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result
    filters = {
        "portfolio_id": "P1" if with_filters else None,
        "business_date": date(2026, 5, 28) if with_filters else None,
        "epoch": 4 if with_filters else None,
    }

    assert await getattr(repository, method_name)(**filters) == []
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    if with_filters:
        assert "portfolio_id = 'p1'" in compiled_query
        assert "date = '2026-05-28'" in compiled_query
        assert "epoch = 4" in compiled_query
    else:
        assert "where" not in compiled_query


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


@pytest.mark.parametrize(("stored_count", "expected_count"), [(7, 7), (None, 0)])
async def test_fetch_authoritative_snapshot_count_returns_normalized_count(
    mock_db_session: AsyncMock,
    stored_count: int | None,
    expected_count: int,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    result = MagicMock()
    result.scalar_one.return_value = stored_count
    mock_db_session.execute.return_value = result

    count = await repository.fetch_authoritative_snapshot_count(
        portfolio_id="P1",
        business_date=date(2026, 5, 28),
        epoch=4,
    )

    assert count == expected_count
    compiled_query = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "row_number() over" in compiled_query
    assert "daily_position_snapshots.portfolio_id = 'p1'" in compiled_query
    assert "daily_position_snapshots.date <= '2026-05-28'" in compiled_query
    assert "daily_position_snapshots.epoch <= 4" in compiled_query
