"""Characterize position timeseries generation persistence contracts."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import PositionTimeseries
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_derived_state_service.app.infrastructure import (
    timeseries_generation_repository,
)

TimeseriesGenerationRepository = timeseries_generation_repository.TimeseriesGenerationRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a versatile mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()

    mock_result.scalars.return_value.all.return_value = [
        MagicMock(portfolio_id="P1", aggregation_date=date(2025, 1, 1), id=1),
        MagicMock(portfolio_id="P2", aggregation_date=date(2025, 1, 2), id=2),
    ]
    mock_result.scalars.return_value.first.return_value = "item1"
    mock_result.mappings.return_value.all.return_value = [
        {"id": 1, "portfolio_id": "P1", "aggregation_date": date(2025, 1, 1)}
    ]
    mock_result.scalar.return_value = True
    mock_result.fetchall.return_value = []
    mock_result.rowcount = 1

    session.execute = AsyncMock(return_value=mock_result)

    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> TimeseriesGenerationRepository:
    """Provides an instance of the repository with a mock session."""
    return TimeseriesGenerationRepository(mock_db_session)


async def test_get_instruments_by_ids_trims_security_ids(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    await repository.get_instruments_by_ids([" S1 ", "", " S2 "])

    compiled_query = str(
        mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(instruments.security_id) IN ('S1', 'S2')" in compiled_query


async def test_get_instruments_by_ids_skips_empty_security_ids(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    instruments = await repository.get_instruments_by_ids([" ", ""])

    assert instruments == []
    mock_db_session.execute.assert_not_awaited()


async def test_get_position_timeseries_for_dates_filters_exact_dates_and_epoch(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    dated_row = MagicMock(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 1, 10),
        epoch=14,
        bod_market_value=Decimal("100"),
        bod_cashflow_position=Decimal("1"),
        eod_cashflow_position=Decimal("2"),
        bod_cashflow_portfolio=Decimal("3"),
        eod_cashflow_portfolio=Decimal("4"),
        eod_market_value=Decimal("110"),
        fees=Decimal("5"),
        quantity=Decimal("10"),
        cost=Decimal("9"),
    )
    mock_db_session.execute.return_value.scalars.return_value.all.return_value = [dated_row]

    await repository.get_position_timeseries_for_dates(
        "P1",
        "S1",
        [date(2025, 1, 10), date(2025, 1, 11)],
        14,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "position_timeseries.portfolio_id = 'P1'" in compiled_query
    assert "position_timeseries.security_id = 'S1'" in compiled_query
    assert "position_timeseries.date IN ('2025-01-10', '2025-01-11')" in compiled_query
    assert "position_timeseries.epoch = 14" in compiled_query


async def test_invalidation_removes_exact_position_and_portfolio_days(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    first_date = date(2025, 1, 10)
    second_date = date(2025, 1, 11)
    position_result = MagicMock()
    position_result.fetchall.return_value = [(first_date,)]
    portfolio_result = MagicMock()
    portfolio_result.fetchall.return_value = [(first_date,), (second_date,)]
    mock_db_session.execute.side_effect = [position_result, portfolio_result]

    invalidated_dates = await repository.invalidate_numeric_materializations(
        "P1",
        "S1",
        [second_date, first_date, first_date],
        14,
    )

    assert invalidated_dates == {first_date, second_date}
    position_statement, portfolio_statement = (
        call.args[0] for call in mock_db_session.execute.await_args_list
    )
    compiled_position = str(
        position_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    compiled_portfolio = str(
        portfolio_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "DELETE FROM position_timeseries" in compiled_position
    assert "position_timeseries.portfolio_id = 'P1'" in compiled_position
    assert "position_timeseries.security_id = 'S1'" in compiled_position
    assert "position_timeseries.date IN ('2025-01-10', '2025-01-11')" in compiled_position
    assert "position_timeseries.epoch = 14" in compiled_position
    assert "DELETE FROM portfolio_timeseries" in compiled_portfolio
    assert "portfolio_timeseries.portfolio_id = 'P1'" in compiled_portfolio
    assert "portfolio_timeseries.date IN ('2025-01-10', '2025-01-11')" in compiled_portfolio
    assert "portfolio_timeseries.epoch = 14" in compiled_portfolio


async def test_invalidation_skips_empty_date_set(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    assert await repository.invalidate_numeric_materializations("P1", "S1", [], 14) == set()
    mock_db_session.execute.assert_not_awaited()


async def test_unavailable_carry_forward_invalidation_is_bounded_and_epoch_scoped(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value.rowcount = 2

    invalidated_count = (
        await repository.invalidate_portfolio_materializations_in_carry_forward_interval(
            "PORT_TS_POS_01",
            start_date=date(2025, 8, 12),
            end_date_exclusive=date(2025, 8, 16),
            excluded_dates=[date(2025, 8, 12), date(2025, 8, 13), date(2025, 8, 13)],
            epoch=4,
        )
    )

    statement = mock_db_session.execute.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert invalidated_count == 2
    assert "DELETE FROM portfolio_timeseries" in compiled
    assert "portfolio_timeseries.portfolio_id = 'PORT_TS_POS_01'" in compiled
    assert "portfolio_timeseries.date >= '2025-08-12'" in compiled
    assert "portfolio_timeseries.date < '2025-08-16'" in compiled
    assert "portfolio_timeseries.date NOT IN ('2025-08-12', '2025-08-13')" in compiled
    assert "portfolio_timeseries.epoch = 4" in compiled


async def test_unavailable_carry_forward_invalidation_skips_empty_interval(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    count = await repository.invalidate_portfolio_materializations_in_carry_forward_interval(
        "PORT_TS_POS_01",
        start_date=date(2025, 8, 12),
        end_date_exclusive=date(2025, 8, 12),
        excluded_dates=[],
        epoch=4,
    )

    assert count == 0
    mock_db_session.execute.assert_not_awaited()


async def test_get_position_timeseries_for_dates_returns_immutable_records(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    row = MagicMock(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 1, 10),
        epoch=14,
        bod_market_value=Decimal("100"),
        bod_cashflow_position=Decimal("1"),
        eod_cashflow_position=Decimal("2"),
        bod_cashflow_portfolio=Decimal("3"),
        eod_cashflow_portfolio=Decimal("4"),
        eod_market_value=Decimal("110"),
        fees=Decimal("5"),
        quantity=Decimal("10"),
        cost=Decimal("9"),
    )
    mock_db_session.execute.return_value.scalars.return_value.all.return_value = [row]

    records = await repository.get_position_timeseries_for_dates(
        "P1", "S1", [date(2025, 1, 10)], 14
    )

    assert records[date(2025, 1, 10)].portfolio_id == "P1"
    assert records[date(2025, 1, 10)].eod_market_value == Decimal("110")
    assert records[date(2025, 1, 10)] is not row


async def test_get_fx_rate_uses_normalized_functional_index_predicates(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    """Verifies the query for the latest FX rate."""
    mock_db_session.execute.return_value.scalars.return_value.first.return_value = MagicMock(
        rate=Decimal("1.25")
    )
    await repository.get_fx_rate(" usd ", " eur ", date(2025, 1, 10))
    compiled_query = str(
        mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "upper(trim(fx_rates.from_currency)) = 'usd'" in compiled_query
    assert "upper(trim(fx_rates.to_currency)) = 'eur'" in compiled_query
    assert "fx_rates.rate_date <= '2025-01-10'" in compiled_query
    assert "order by fx_rates.rate_date desc, fx_rates.id desc" in compiled_query


async def test_upsert_position_timeseries(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    """Verifies the construction of the position timeseries upsert statement."""
    record = PositionTimeseries(
        portfolio_id="P1", security_id="S1", date=date(2025, 1, 10), epoch=1
    )
    await repository.upsert_position_timeseries(record)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_stmt = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "INSERT INTO position_timeseries" in compiled_stmt
    # --- FIX: Assert for the correct primary key including epoch ---
    assert "ON CONFLICT (portfolio_id, security_id, date, epoch) DO UPDATE" in compiled_stmt


async def test_get_all_cashflows_for_security_date_uses_latest_cashflow_epoch_within_target_epoch(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    await repository.get_all_cashflows_for_security_date("P1", "S1", date(2025, 1, 10), 14)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "cashflows.epoch <= 14" in compiled_query
    assert "trim(cashflows.portfolio_id) = 'P1'" in compiled_query
    assert "trim(cashflows.security_id) = 'S1'" in compiled_query
    assert (
        "row_number() OVER (PARTITION BY cashflows.transaction_id ORDER BY cashflows.epoch DESC)"
        in compiled_query
    )
    assert "cashflows.id = anon_1.id" in compiled_query
    assert "anon_1.rn = 1" in compiled_query


async def test_get_cashflows_for_security_dates_filters_exact_dates_and_epoch(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    dated_row = MagicMock(
        transaction_id="TX1",
        cashflow_date=date(2025, 1, 10),
        epoch=14,
        amount=Decimal("25"),
        classification="INCOME",
        timing="EOD",
        is_position_flow=True,
        is_portfolio_flow=False,
    )
    mock_db_session.execute.return_value.scalars.return_value.all.return_value = [dated_row]

    result = await repository.get_cashflows_for_security_dates(
        "P1",
        "S1",
        [date(2025, 1, 10), date(2025, 1, 11)],
        14,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "trim(cashflows.portfolio_id) = 'P1'" in compiled_query
    assert "trim(cashflows.security_id) = 'S1'" in compiled_query
    assert "cashflows.cashflow_date IN ('2025-01-10', '2025-01-11')" in compiled_query
    assert "cashflows.epoch <= 14" in compiled_query
    assert result[date(2025, 1, 10)][0].transaction_id == "TX1"
    assert result[date(2025, 1, 10)][0] is not dated_row
    assert result[date(2025, 1, 11)] == []


async def test_get_last_snapshot_before_uses_latest_snapshot_not_exceeding_target_epoch(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    mock_db_session.execute.return_value.scalars.return_value.first.return_value = MagicMock(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 1, 9),
        epoch=13,
        quantity=Decimal("10"),
        cost_basis_local=Decimal("90"),
        market_value_local=Decimal("100"),
    )
    await repository.get_last_snapshot_before("P1", "S1", date(2025, 1, 10), 14)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "daily_position_snapshots.epoch <= 14" in compiled_query
    assert "trim(daily_position_snapshots.portfolio_id) = 'P1'" in compiled_query
    assert "trim(daily_position_snapshots.security_id) = 'S1'" in compiled_query
    assert (
        "ORDER BY daily_position_snapshots.date DESC, daily_position_snapshots.epoch DESC"
        in compiled_query
    )


async def test_get_next_snapshots_after_uses_latest_epoch_per_future_date(
    repository: TimeseriesGenerationRepository, mock_db_session: AsyncMock
):
    mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
    await repository.get_next_snapshots_after("P1", "S1", date(2025, 1, 10), 14, 25)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "daily_position_snapshots.epoch <= 14" in compiled_query
    assert "trim(daily_position_snapshots.portfolio_id) = 'P1'" in compiled_query
    assert "trim(daily_position_snapshots.security_id) = 'S1'" in compiled_query
    assert "daily_position_snapshots.date > '2025-01-10'" in compiled_query
    assert (
        "row_number() OVER (PARTITION BY daily_position_snapshots.date "
        "ORDER BY daily_position_snapshots.epoch DESC)" in compiled_query
    )
    assert "anon_1.rn = 1" in compiled_query
    assert "ORDER BY daily_position_snapshots.date ASC" in compiled_query
    assert "LIMIT 25" in compiled_query


async def test_stage_aggregation_jobs_rearms_completed_day_for_late_material_input(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    await repository.stage_aggregation_jobs(
        "PORT_TS_POS_01",
        [date(2025, 8, 12)],
        4,
        "corr-456",
    )

    executed_stmt = mock_db_session.execute.await_args.args[0]
    compiled = executed_stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    compiled_stmt = str(compiled)
    compiled_values = set(compiled.params.values())

    assert "DO UPDATE SET status" in compiled_stmt
    assert "target_epoch" in compiled_stmt
    assert "source_revision" in compiled_stmt
    assert "greatest(portfolio_aggregation_jobs.target_epoch" in compiled_stmt
    assert "portfolio_aggregation_jobs.source_revision + 1" in compiled_stmt
    assert "correlation_id" in compiled_stmt
    assert "portfolio_aggregation_jobs.status !=" in compiled_stmt
    assert "portfolio_aggregation_jobs.target_epoch =" not in compiled_stmt
    assert "portfolio_aggregation_jobs.target_epoch != excluded.target_epoch" in compiled_stmt
    assert "REPROCESS_REQUESTED" in compiled_stmt or "REPROCESS_REQUESTED" in compiled_values


async def test_carry_forward_restage_is_bounded_and_preserves_active_work(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value.rowcount = 2

    count = await repository.restage_aggregation_jobs_in_carry_forward_interval(
        "PORT_TS_POS_01",
        start_date=date(2025, 8, 12),
        end_date_exclusive=date(2025, 8, 16),
        excluded_dates=[date(2025, 8, 12), date(2025, 8, 14)],
        target_epoch=4,
        correlation_id="  corr-carry-forward  ",
    )

    executed_stmt = mock_db_session.execute.await_args.args[0]
    compiled_stmt = str(
        executed_stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert count == 2
    assert "UPDATE portfolio_aggregation_jobs SET" in compiled_stmt
    assert "portfolio_aggregation_jobs.portfolio_id = 'PORT_TS_POS_01'" in compiled_stmt
    assert "portfolio_aggregation_jobs.aggregation_date >= '2025-08-12'" in compiled_stmt
    assert "portfolio_aggregation_jobs.aggregation_date < '2025-08-16'" in compiled_stmt
    assert "portfolio_aggregation_jobs.status IN" in compiled_stmt
    assert all(
        status in compiled_stmt for status in ("PENDING", "PROCESSING", "COMPLETE", "FAILED")
    )
    assert "portfolio_aggregation_jobs.aggregation_date NOT IN" in compiled_stmt
    assert "greatest(portfolio_aggregation_jobs.target_epoch, 4)" in compiled_stmt
    assert "portfolio_aggregation_jobs.source_revision + 1" in compiled_stmt
    assert "REPROCESS_REQUESTED" in compiled_stmt
    assert "corr-carry-forward" in compiled_stmt
    assert "  corr-carry-forward  " not in compiled_stmt


async def test_carry_forward_restage_skips_empty_interval(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    count = await repository.restage_aggregation_jobs_in_carry_forward_interval(
        "PORT_TS_POS_01",
        start_date=date(2025, 8, 12),
        end_date_exclusive=date(2025, 8, 12),
        excluded_dates=[],
        target_epoch=4,
        correlation_id=None,
    )

    assert count == 0
    mock_db_session.execute.assert_not_awaited()


async def test_aggregation_staging_metrics_distinguish_material_outcomes(monkeypatch) -> None:
    observations: list[tuple[str, str, str, int]] = []
    monkeypatch.setattr(
        timeseries_generation_repository,
        "observe_control_queue_outcome",
        lambda queue, stage, outcome, count: observations.append((queue, stage, outcome, count)),
    )

    timeseries_generation_repository._observe_aggregation_staging_outcomes(
        staged_rows=[
            MagicMock(status="PENDING", attempt_count=0, source_revision=1),
            MagicMock(status="PENDING", attempt_count=2, source_revision=3),
            MagicMock(status="PROCESSING", attempt_count=1, source_revision=4),
        ],
        requested_count=4,
    )

    assert observations == [
        ("aggregation", "staging", "new", 1),
        ("aggregation", "staging", "rearmed", 1),
        ("aggregation", "staging", "superseded", 1),
        ("aggregation", "staging", "no_op", 1),
    ]


async def test_stage_aggregation_jobs_deduplicates_and_orders_dates(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    await repository.stage_aggregation_jobs(
        "PORT_TS_POS_01",
        [date(2025, 8, 14), date(2025, 8, 13), date(2025, 8, 13)],
        4,
        "corr-789",
    )

    executed_stmt = mock_db_session.execute.await_args.args[0]
    compiled_stmt = str(
        executed_stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert compiled_stmt.count("'2025-08-13'") == 1
    assert compiled_stmt.count("'2025-08-14'") == 1
    assert compiled_stmt.index("'2025-08-13'") < compiled_stmt.index("'2025-08-14'")


async def test_stage_aggregation_jobs_records_missing_correlation_diagnostics(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    await repository.stage_aggregation_jobs(
        "PORT_TS_POS_01",
        [date(2025, 8, 12)],
        4,
        None,
    )

    executed_stmt = mock_db_session.execute.await_args.args[0]
    compiled_stmt = str(
        executed_stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "correlation_missing_reason" in compiled_stmt
    assert "alternate_lookup_key" in compiled_stmt
    assert "correlation_id_not_supplied" in compiled_stmt
    assert (
        "aggregation_job|aggregation_date=2025-08-12|portfolio_id=PORT_TS_POS_01" in compiled_stmt
    )


async def test_stage_aggregation_jobs_skips_empty_date_set(
    repository: TimeseriesGenerationRepository,
    mock_db_session: AsyncMock,
) -> None:
    await repository.stage_aggregation_jobs("PORT_TS_POS_01", [], 4, "corr-empty")

    mock_db_session.execute.assert_not_awaited()
