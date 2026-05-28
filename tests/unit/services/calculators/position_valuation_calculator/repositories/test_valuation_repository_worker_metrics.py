from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    return session


async def test_find_and_claim_eligible_jobs_emits_claim_metric(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        MagicMock(
            portfolio_id="PORT_001",
            security_id="AAPL_US",
            valuation_date=date(2026, 3, 3),
            epoch=0,
        ),
        MagicMock(
            portfolio_id="PORT_001",
            security_id="MSFT_US",
            valuation_date=date(2026, 3, 3),
            epoch=0,
        ),
    ]
    mock_db_session.execute.return_value = mock_result

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_jobs_claimed"
    ) as claimed_metric:
        claimed_jobs = await repo.find_and_claim_eligible_jobs(batch_size=50)

    assert len(claimed_jobs) == 2
    claimed_metric.assert_called_once_with(2)

    claim_stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(claim_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "NOT (EXISTS" in compiled_query
    assert "portfolio_valuation_jobs_1.epoch > portfolio_valuation_jobs.epoch" in compiled_query


async def test_find_and_reset_stale_jobs_emits_reset_metric(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [
        MagicMock(id=101, attempt_count=1, has_newer_epoch=False),
        MagicMock(id=102, attempt_count=1, has_newer_epoch=False),
        MagicMock(id=103, attempt_count=1, has_newer_epoch=False),
    ]
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(101,), (102,), (103,)]
    mock_db_session.execute.side_effect = [select_result, mock_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)

    assert reset_count == 3
    reset_metric.assert_called_once_with(3)


async def test_find_and_reset_stale_jobs_marks_over_limit_rows_failed(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [MagicMock(id=201, attempt_count=3, has_newer_epoch=False)]
    failed_result = MagicMock()
    mock_db_session.execute.side_effect = [select_result, failed_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)

    assert reset_count == 0
    reset_metric.assert_not_called()


async def test_find_and_reset_stale_jobs_skips_superseded_rows_without_emitting_reset_metric(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [MagicMock(id=301, attempt_count=1, has_newer_epoch=True)]
    skipped_result = MagicMock()
    mock_db_session.execute.side_effect = [select_result, skipped_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)

    assert reset_count == 0
    reset_metric.assert_not_called()


async def test_find_and_reset_stale_jobs_rechecks_processing_state_before_reset(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [MagicMock(id=101, attempt_count=1, has_newer_epoch=False)]
    update_result = MagicMock()
    update_result.fetchall.return_value = []
    mock_db_session.execute.side_effect = [select_result, update_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)

    assert reset_count == 0
    reset_metric.assert_not_called()
    update_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_query = str(update_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in compiled_query


async def test_get_job_queue_stats_returns_pending_failed_and_oldest_pending(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    oldest_pending = datetime(2026, 3, 3, tzinfo=timezone.utc)

    row = MagicMock(
        pending_count=5,
        failed_count=2,
        oldest_pending_created_at=oldest_pending,
    )
    result = MagicMock()
    result.one.return_value = row
    mock_db_session.execute.return_value = result

    queue_stats = await repo.get_job_queue_stats()

    assert queue_stats == {
        "pending_count": 5,
        "failed_count": 2,
        "oldest_pending_created_at": oldest_pending,
    }
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs_1.epoch > portfolio_valuation_jobs.epoch" in compiled_query


async def test_get_fx_rate_normalizes_currency_codes_and_uses_functional_index_predicates(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    fx_rate = await repo.get_fx_rate(
        from_currency=" eur ",
        to_currency=" usd ",
        a_date=date(2026, 3, 27),
    )

    assert fx_rate is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "upper(trim(fx_rates.from_currency)) = 'EUR'" in compiled_query
    assert "upper(trim(fx_rates.to_currency)) = 'USD'" in compiled_query
    assert "fx_rates.rate_date <= '2026-03-27'" in compiled_query
    assert "ORDER BY fx_rates.rate_date DESC" in compiled_query


async def test_get_instrument_trims_security_id_before_query(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    instrument = await repo.get_instrument(" SEC_A ")

    assert instrument is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(instruments.security_id) = 'SEC_A'" in compiled_query


async def test_get_portfolio_trims_portfolio_id_before_query(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    portfolio = await repo.get_portfolio(" PORT_001 ")

    assert portfolio is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(portfolios.portfolio_id) = 'PORT_001'" in compiled_query


async def test_get_portfolios_by_ids_trims_portfolio_ids_and_skips_blanks(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result

    portfolios = await repo.get_portfolios_by_ids([" PORT_001 ", "", " PORT_002 "])

    assert portfolios == []
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(portfolios.portfolio_id) IN ('PORT_001', 'PORT_002')" in compiled_query


async def test_get_portfolios_by_ids_skips_empty_identifier_list(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    portfolios = await repo.get_portfolios_by_ids([" ", ""])

    assert portfolios == []
    mock_db_session.execute.assert_not_awaited()


async def test_get_last_position_history_before_date_trims_portfolio_and_security_ids(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    history = await repo.get_last_position_history_before_date(
        " PORT_001 ", " SEC_A ", date(2026, 3, 27), 42
    )

    assert history is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(position_history.portfolio_id) = 'PORT_001'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC_A'" in compiled_query
    assert "position_history.position_date <= '2026-03-27'" in compiled_query
    assert "position_history.epoch = 42" in compiled_query


async def test_update_job_status_trims_portfolio_and_security_ids(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.rowcount = 1
    mock_db_session.execute.return_value = result

    updated = await repo.update_job_status(
        portfolio_id=" PORT_001 ",
        security_id=" SEC_A ",
        valuation_date=date(2026, 3, 27),
        epoch=42,
        status="COMPLETED",
    )

    assert updated is True
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(portfolio_valuation_jobs.portfolio_id) = 'PORT_001'" in compiled_query
    assert "trim(portfolio_valuation_jobs.security_id) = 'SEC_A'" in compiled_query
    assert "portfolio_valuation_jobs.valuation_date = '2026-03-27'" in compiled_query
    assert "portfolio_valuation_jobs.epoch = 42" in compiled_query
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in compiled_query


async def test_get_latest_price_for_position_trims_security_id_before_query(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    market_price = await repo.get_latest_price_for_position(
        security_id=" SEC_A ",
        position_date=date(2026, 3, 27),
    )

    assert market_price is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(market_prices.security_id) = 'SEC_A'" in compiled_query
    assert "market_prices.price_date <= '2026-03-27'" in compiled_query
    assert "ORDER BY market_prices.price_date DESC" in compiled_query


async def test_get_next_price_date_trims_security_id_before_query(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = result

    next_price_date = await repo.get_next_price_date(
        security_id=" SEC_A ",
        after_date=date(2026, 3, 27),
    )

    assert next_price_date is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(market_prices.security_id) = 'SEC_A'" in compiled_query
    assert "market_prices.price_date > '2026-03-27'" in compiled_query
    assert "ORDER BY market_prices.price_date ASC" in compiled_query
    assert "LIMIT 1" in compiled_query
