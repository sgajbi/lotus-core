from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PositionState,
    PositionTimeseries,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.timeseries_generator_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)

pytestmark = pytest.mark.asyncio


def _snapshot(
    portfolio_id: str, security_id: str, a_date: date, *, epoch: int = 0
) -> DailyPositionSnapshot:
    return DailyPositionSnapshot(
        portfolio_id=portfolio_id,
        security_id=security_id,
        date=a_date,
        epoch=epoch,
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
        market_price=Decimal("10"),
        market_value=Decimal("100"),
        market_value_local=Decimal("100"),
        unrealized_gain_loss=Decimal("0"),
        unrealized_gain_loss_local=Decimal("0"),
        valuation_status="VALUED",
    )


def _position_ts(
    portfolio_id: str, security_id: str, a_date: date, *, epoch: int = 0
) -> PositionTimeseries:
    return PositionTimeseries(
        portfolio_id=portfolio_id,
        security_id=security_id,
        date=a_date,
        epoch=epoch,
        bod_market_value=Decimal("100"),
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=Decimal("100"),
        fees=Decimal("0"),
        quantity=Decimal("10"),
        cost=Decimal("100"),
    )


def _transaction(
    transaction_id: str,
    portfolio_id: str,
    security_id: str,
    transaction_date: date,
    *,
    transaction_type: str = "BUY",
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        quantity=Decimal("1"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        currency="USD",
    )


@pytest.fixture(scope="function")
def setup_sequential_jobs_with_snapshot_completeness(db_engine, clean_db):
    portfolio_id = "SEQ_JOB_TEST_01"
    day1 = date(2025, 8, 18)
    day2 = date(2025, 8, 19)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    epoch=0,
                    watermark_date=date(2024, 1, 1),
                ),
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    epoch=0,
                    watermark_date=date(2024, 1, 1),
                ),
            ]
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    portfolio_id=portfolio_id, aggregation_date=day1, status="PENDING"
                ),
                PortfolioAggregationJob(
                    portfolio_id=portfolio_id, aggregation_date=day2, status="PENDING"
                ),
            ]
        )
        session.flush()

        # Day1 inputs: 2 expected snapshots, only 1 produced position-timeseries (incomplete).
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", day1),
                _snapshot(portfolio_id, "SEC_B", day1),
                _position_ts(portfolio_id, "SEC_A", day1),
            ]
        )
        # Day2 inputs: complete latest-per-security input set. Portfolio aggregation
        # no longer depends on a previous portfolio row, so complete days can be
        # claimed in the same batch and processed in parallel by Kafka consumers.
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", day2),
                _snapshot(portfolio_id, "SEC_B", day2),
                _position_ts(portfolio_id, "SEC_A", day2),
                _position_ts(portfolio_id, "SEC_B", day2),
            ]
        )
        session.commit()

    return {"portfolio_id": portfolio_id, "day1": day1, "day2": day2}


async def test_find_and_claim_eligible_jobs_enforces_snapshot_completeness_gate(
    setup_sequential_jobs_with_snapshot_completeness,
    async_db_session: AsyncSession,
    db_engine,
):
    repo = TimeseriesRepository(async_db_session)
    portfolio_id = setup_sequential_jobs_with_snapshot_completeness["portfolio_id"]
    day1 = setup_sequential_jobs_with_snapshot_completeness["day1"]
    day2 = setup_sequential_jobs_with_snapshot_completeness["day2"]

    # Day1 should not claim while input set is incomplete, but complete later
    # dates are independently eligible because portfolio aggregation does not
    # carry prior portfolio rows forward.
    claimed_jobs_1 = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()
    assert [job.aggregation_date for job in claimed_jobs_1] == [day2]

    # Complete day1 input set.
    with Session(db_engine) as session:
        session.add(_position_ts(portfolio_id, "SEC_B", day1))
        session.commit()
    await async_db_session.rollback()

    claimed_jobs_2 = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()
    assert [job.aggregation_date for job in claimed_jobs_2] == [day1]


async def test_find_and_claim_eligible_jobs_claims_first_day_without_portfolio_history(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "FIRST_DAY_PORTFOLIO"
    first_day = date(2025, 8, 19)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.flush()
        session.add(
            Instrument(
                security_id="CASH_USD_FIRST",
                name="Cash USD",
                isin="CASH_USD_FIRST",
                currency="USD",
                product_type="Cash",
            )
        )
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id="CASH_USD_FIRST",
                epoch=0,
                watermark_date=date(1970, 1, 1),
            )
        )
        session.add(
            PortfolioAggregationJob(
                portfolio_id=portfolio_id,
                aggregation_date=first_day,
                status="PENDING",
            )
        )
        session.add(_snapshot(portfolio_id, "CASH_USD_FIRST", first_day, epoch=0))
        session.add(_position_ts(portfolio_id, "CASH_USD_FIRST", first_day, epoch=0))
        session.commit()

    repo = TimeseriesRepository(async_db_session)
    claimed_jobs = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()

    assert len(claimed_jobs) == 1
    assert claimed_jobs[0].aggregation_date == first_day


async def test_find_and_claim_eligible_jobs_accepts_mixed_latest_epochs_per_security(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "MIXED_EPOCH_PORT"
    a_date = date(2025, 8, 23)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.flush()
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    epoch=1,
                    watermark_date=a_date,
                ),
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    epoch=0,
                    watermark_date=date(1970, 1, 1),
                ),
            ]
        )
        session.add(
            PortfolioAggregationJob(
                portfolio_id=portfolio_id, aggregation_date=a_date, status="PENDING"
            )
        )
        session.add(
            PortfolioTimeseries(
                portfolio_id=portfolio_id,
                date=date(2025, 8, 22),
                epoch=1,
                bod_market_value=Decimal("0"),
                bod_cashflow=Decimal("0"),
                eod_cashflow=Decimal("0"),
                eod_market_value=Decimal("100"),
                fees=Decimal("0"),
            )
        )
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", a_date, epoch=1),
                _snapshot(portfolio_id, "SEC_B", a_date, epoch=0),
                _position_ts(portfolio_id, "SEC_A", a_date, epoch=1),
                _position_ts(portfolio_id, "SEC_B", a_date, epoch=0),
            ]
        )
        session.commit()

    repo = TimeseriesRepository(async_db_session)
    claimed_jobs = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()

    assert len(claimed_jobs) == 1
    assert claimed_jobs[0].aggregation_date == a_date


async def test_find_and_claim_eligible_jobs_claims_all_complete_days_without_history_dependency(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "STRANDED_BOOTSTRAP_PORT"
    early_day = date(2025, 4, 1)
    later_day = date(2025, 7, 2)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.flush()
        session.add(
            Instrument(
                security_id="CASH_USD_BOOT",
                name="Cash USD",
                isin="CASH_USD_BOOT",
                currency="USD",
                product_type="Cash",
            )
        )
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id="CASH_USD_BOOT",
                epoch=0,
                watermark_date=date(1970, 1, 1),
            )
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    portfolio_id=portfolio_id,
                    aggregation_date=early_day,
                    status="PENDING",
                ),
                PortfolioAggregationJob(
                    portfolio_id=portfolio_id,
                    aggregation_date=later_day,
                    status="PENDING",
                ),
            ]
        )
        session.add_all(
            [
                _snapshot(portfolio_id, "CASH_USD_BOOT", early_day, epoch=0),
                _position_ts(portfolio_id, "CASH_USD_BOOT", early_day, epoch=0),
                _snapshot(portfolio_id, "CASH_USD_BOOT", later_day, epoch=0),
                _position_ts(portfolio_id, "CASH_USD_BOOT", later_day, epoch=0),
                PortfolioTimeseries(
                    portfolio_id=portfolio_id,
                    date=later_day,
                    epoch=0,
                    bod_market_value=Decimal("0"),
                    bod_cashflow=Decimal("0"),
                    eod_cashflow=Decimal("0"),
                    eod_market_value=Decimal("100"),
                    fees=Decimal("0"),
                ),
            ]
        )
        session.commit()

    repo = TimeseriesRepository(async_db_session)
    claimed_jobs = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()

    assert [job.aggregation_date for job in claimed_jobs] == [early_day, later_day]


async def test_find_and_claim_eligible_jobs_does_not_need_prior_day_when_current_epoch_has_advanced(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "PRIOR_DAY_MIXED_EPOCH"
    prior_day = date(2025, 8, 22)
    target_day = date(2025, 8, 23)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.flush()
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    epoch=1,
                    watermark_date=target_day,
                ),
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    epoch=0,
                    watermark_date=date(1970, 1, 1),
                ),
            ]
        )
        session.add(
            PortfolioAggregationJob(
                portfolio_id=portfolio_id, aggregation_date=target_day, status="PENDING"
            )
        )
        session.add(
            PortfolioTimeseries(
                portfolio_id=portfolio_id,
                date=prior_day,
                epoch=0,
                bod_market_value=Decimal("0"),
                bod_cashflow=Decimal("0"),
                eod_cashflow=Decimal("0"),
                eod_market_value=Decimal("170"),
                fees=Decimal("0"),
            )
        )
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", target_day, epoch=1),
                _snapshot(portfolio_id, "SEC_B", target_day, epoch=0),
                _position_ts(portfolio_id, "SEC_A", target_day, epoch=1),
                _position_ts(portfolio_id, "SEC_B", target_day, epoch=0),
            ]
        )
        session.commit()

    repo = TimeseriesRepository(async_db_session)
    claimed_jobs = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()

    assert len(claimed_jobs) == 1
    assert claimed_jobs[0].aggregation_date == target_day


async def test_get_all_position_timeseries_for_date_returns_one_authoritative_asof_row_per_security(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "PTS_ASOF_PORT"
    target_date = date(2025, 8, 20)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    date=date(2025, 8, 18),
                    epoch=1,
                    bod_market_value=Decimal("10"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("11"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    cost=Decimal("10"),
                ),
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    date=date(2025, 8, 19),
                    epoch=1,
                    bod_market_value=Decimal("20"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("21"),
                    fees=Decimal("0"),
                    quantity=Decimal("2"),
                    cost=Decimal("20"),
                ),
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    date=date(2025, 8, 19),
                    epoch=2,
                    bod_market_value=Decimal("30"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("31"),
                    fees=Decimal("0"),
                    quantity=Decimal("3"),
                    cost=Decimal("30"),
                ),
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    date=date(2025, 8, 17),
                    epoch=4,
                    bod_market_value=Decimal("40"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("41"),
                    fees=Decimal("0"),
                    quantity=Decimal("4"),
                    cost=Decimal("40"),
                ),
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    date=date(2025, 8, 21),
                    epoch=1,
                    bod_market_value=Decimal("50"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("51"),
                    fees=Decimal("0"),
                    quantity=Decimal("5"),
                    cost=Decimal("50"),
                ),
            ]
        )
        session.commit()

    repo = TimeseriesRepository(async_db_session)

    rows = await repo.get_all_position_timeseries_for_date(portfolio_id, target_date, 4)

    assert [(row.security_id, row.date, row.epoch) for row in rows] == [
        ("SEC_A", date(2025, 8, 19), 2),
        ("SEC_B", date(2025, 8, 17), 4),
    ]
    assert len(rows) == 2


async def test_get_all_cashflows_for_security_date_returns_latest_restatement_per_transaction_id(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "CF_ASOF_PORT"
    security_id = "CASH_USD"
    cashflow_date = date(2025, 8, 20)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name="Cash USD",
                isin="CASH_USD",
                currency="USD",
                product_type="Cash",
            )
        )
        session.add_all(
            [
                _transaction("TXN_RESTATED", portfolio_id, security_id, cashflow_date),
                _transaction("TXN_SECOND", portfolio_id, security_id, cashflow_date),
                _transaction("TXN_FUTURE", portfolio_id, security_id, cashflow_date),
            ]
        )
        session.add_all(
            [
                Cashflow(
                    transaction_id="TXN_RESTATED",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    cashflow_date=cashflow_date,
                    epoch=1,
                    amount=Decimal("100"),
                    currency="USD",
                    classification="CASHFLOW_OUT",
                    timing="BOD",
                    calculation_type="NET",
                    is_position_flow=False,
                    is_portfolio_flow=True,
                ),
                Cashflow(
                    transaction_id="TXN_RESTATED",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    cashflow_date=cashflow_date,
                    epoch=2,
                    amount=Decimal("100"),
                    currency="USD",
                    classification="EXPENSE",
                    timing="EOD",
                    calculation_type="NET",
                    is_position_flow=False,
                    is_portfolio_flow=False,
                ),
                Cashflow(
                    transaction_id="TXN_SECOND",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    cashflow_date=cashflow_date,
                    epoch=1,
                    amount=Decimal("250"),
                    currency="USD",
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    calculation_type="NET",
                    is_position_flow=False,
                    is_portfolio_flow=True,
                ),
                Cashflow(
                    transaction_id="TXN_FUTURE",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    cashflow_date=cashflow_date,
                    epoch=3,
                    amount=Decimal("999"),
                    currency="USD",
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    calculation_type="NET",
                    is_position_flow=False,
                    is_portfolio_flow=True,
                ),
            ]
        )
        session.commit()

    repo = TimeseriesRepository(async_db_session)

    rows = await repo.get_all_cashflows_for_security_date(
        portfolio_id, security_id, cashflow_date, 2
    )

    assert [(row.transaction_id, row.epoch) for row in rows] == [
        ("TXN_SECOND", 1),
        ("TXN_RESTATED", 2),
    ]
    restated_row = next(row for row in rows if row.transaction_id == "TXN_RESTATED")
    assert restated_row.classification == "EXPENSE"
    assert restated_row.timing == "EOD"
    assert restated_row.is_portfolio_flow is False
    assert all(row.transaction_id != "TXN_FUTURE" for row in rows)
