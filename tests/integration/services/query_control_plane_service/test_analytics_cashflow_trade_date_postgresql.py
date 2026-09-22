"""Trade-date position analytics must not inherit settlement-ledger chronology."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    BusinessDate,
    Cashflow,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    Transaction,
)
from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.application.analytics.analytics_timeseries_service import (  # noqa: E501
    AnalyticsRuntimePolicy,
    AnalyticsTimeseriesService,
)
from src.services.query_control_plane_service.app.contracts.analytics_inputs import (
    AnalyticsWindow,
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)
from src.services.query_control_plane_service.app.domain.analytics import (
    AnalyticsCashflowEpochEvidenceError,
)
from src.services.query_control_plane_service.app.infrastructure import (
    analytics_timeseries_repository,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_export_repository import (  # noqa: E501
    AnalyticsExportRepository,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_unit_of_work import (  # noqa: E501
    SqlAlchemyAnalyticsUnitOfWork,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct, pytest.mark.lifecycle]

PORTFOLIO = "TRADE_DATE_ANALYTICS_PG"
TRADE_DAY = date(2026, 4, 10)
SETTLEMENT_DAY = date(2026, 4, 12)
DEPOSIT_DAY = date(2026, 4, 13)
INCOME_PRIOR_DAY = date(2026, 3, 10)
INCOME_DAY = date(2026, 3, 11)
ACQUISITION_DAY = date(2026, 3, 12)
ACQUISITION_SETTLEMENT_DAY = ACQUISITION_DAY + timedelta(days=2)


def _transaction(transaction_id: str, security_id: str, transaction_type: str) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id=PORTFOLIO,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 10, 23, 30, tzinfo=UTC),
        settlement_date=datetime(2026, 4, 12, 16, tzinfo=UTC),
        transaction_type=transaction_type,
        quantity=Decimal("1"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
    )


def _cashflow(
    transaction_id: str,
    security_id: str,
    *,
    flow_date: date,
    classification: str,
    timing: str,
    amount: str,
    epoch: int = 0,
    portfolio_flow: bool = False,
) -> Cashflow:
    return Cashflow(
        transaction_id=transaction_id,
        portfolio_id=PORTFOLIO,
        security_id=security_id,
        cashflow_date=flow_date,
        epoch=epoch,
        amount=Decimal(amount),
        currency="USD",
        classification=classification,
        timing=timing,
        calculation_type="SOURCE",
        is_position_flow=True,
        is_portfolio_flow=portfolio_flow,
    )


async def test_paired_internal_open_is_selected_from_postgresql_for_both_source_products(
    clean_db, async_db_session: AsyncSession
) -> None:
    session = async_db_session
    session.add(
        Portfolio(
            tenant_id="tenant-cash-income",
            portfolio_id=PORTFOLIO,
            base_currency="USD",
            open_date=INCOME_PRIOR_DAY,
            risk_exposure="moderate",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="Singapore",
            client_id="CLIENT_CASH_INCOME",
            status="ACTIVE",
        )
    )
    session.add_all(
        [
            Instrument(
                security_id=security_id,
                name=security_id,
                isin=isin,
                currency="USD",
                product_type=product_type,
                asset_class=asset_class,
            )
            for security_id, isin, product_type, asset_class in (
                ("CASH", "CASH-INCOME-PG", "CASH", "Cash"),
                ("BOND", "BOND-INCOME-PG", "BOND", "Fixed Income"),
                ("EQUITY", "EQUITY-ACQUISITION-PG", "EQUITY", "Equity"),
            )
        ]
    )
    session.add_all(
        BusinessDate(date=day) for day in (INCOME_PRIOR_DAY, INCOME_DAY, ACQUISITION_DAY)
    )
    await session.flush()
    session.add_all(
        [
            Transaction(
                transaction_id=transaction_id,
                portfolio_id=PORTFOLIO,
                instrument_id=security_id,
                security_id=security_id,
                transaction_date=datetime(day.year, day.month, day.day, 9, tzinfo=UTC),
                settlement_date=datetime.combine(
                    ACQUISITION_SETTLEMENT_DAY if day == ACQUISITION_DAY else day,
                    time(16),
                    tzinfo=UTC,
                ),
                transaction_type=transaction_type,
                quantity=Decimal("10"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("10"),
                trade_currency="USD",
                currency="USD",
            )
            for transaction_id, security_id, transaction_type, day in (
                ("INCOME-CASH", "CASH", "BUY", INCOME_DAY),
                ("INCOME-BOND", "BOND", "INTEREST", INCOME_DAY),
                ("ACQUISITION-CASH", "CASH", "SELL", ACQUISITION_DAY),
                ("ACQUISITION-EQUITY", "EQUITY", "BUY", ACQUISITION_DAY),
            )
        ]
    )
    await session.flush()
    session.add_all(
        [
            PositionState(
                portfolio_id=PORTFOLIO,
                security_id=security_id,
                epoch=1,
                watermark_date=ACQUISITION_DAY,
                status="CURRENT",
            )
            for security_id in ("CASH", "BOND", "EQUITY")
        ]
    )
    for day, security_id, bod, eod, flow, quantity, transaction_id in (
        (INCOME_PRIOR_DAY, "CASH", "100", "100", "0", "100", "INCOME-CASH"),
        (INCOME_PRIOR_DAY, "BOND", "400", "400", "0", "1", "INCOME-BOND"),
        (INCOME_DAY, "CASH", "100", "110", "10", "110", "INCOME-CASH"),
        (INCOME_DAY, "BOND", "400", "404", "0", "1", "INCOME-BOND"),
        (ACQUISITION_DAY, "CASH", "110", "60", "0", "60", "ACQUISITION-CASH"),
        (ACQUISITION_DAY, "BOND", "404", "406", "0", "1", "INCOME-BOND"),
        (ACQUISITION_DAY, "EQUITY", "0", "49", "0", "1", "ACQUISITION-EQUITY"),
    ):
        session.add(
            PositionHistory(
                portfolio_id=PORTFOLIO,
                security_id=security_id,
                transaction_id=transaction_id,
                position_date=day,
                epoch=1,
                quantity=Decimal(quantity),
                cost_basis=Decimal(eod),
                cost_basis_local=Decimal(eod),
            )
        )
        session.add(
            PositionTimeseries(
                portfolio_id=PORTFOLIO,
                security_id=security_id,
                date=day,
                epoch=1,
                bod_market_value=Decimal(bod),
                bod_cashflow_position=Decimal(flow),
                eod_cashflow_position=(
                    Decimal("-10")
                    if security_id == "BOND" and day == INCOME_DAY
                    else Decimal("-50")
                    if security_id == "CASH" and day == ACQUISITION_DAY
                    else Decimal("0")
                ),
                bod_cashflow_portfolio=Decimal("0"),
                eod_cashflow_portfolio=Decimal("0"),
                eod_market_value=Decimal(eod),
                fees=Decimal("0"),
                quantity=Decimal(quantity),
                cost=Decimal("1"),
            )
        )
    session.add_all(
        [
            _cashflow(
                transaction_id,
                security_id,
                flow_date=day,
                classification=classification,
                timing=timing,
                amount=amount,
                epoch=1,
            )
            for transaction_id, security_id, day, classification, timing, amount in (
                ("INCOME-CASH", "CASH", INCOME_DAY, "INVESTMENT_OUTFLOW", "BOD", "-10"),
                ("INCOME-BOND", "BOND", INCOME_DAY, "INCOME", "EOD", "10"),
                (
                    "ACQUISITION-CASH",
                    "CASH",
                    ACQUISITION_SETTLEMENT_DAY,
                    "INVESTMENT_INFLOW",
                    "EOD",
                    "50",
                ),
                (
                    "ACQUISITION-EQUITY",
                    "EQUITY",
                    ACQUISITION_SETTLEMENT_DAY,
                    "INVESTMENT_OUTFLOW",
                    "BOD",
                    "-50",
                ),
            )
        ]
    )
    await session.commit()

    reader = analytics_timeseries_repository.AnalyticsTimeseriesRepository(session)
    service = AnalyticsTimeseriesService(
        reader=reader,
        export_store=AnalyticsExportRepository(session),
        unit_of_work=SqlAlchemyAnalyticsUnitOfWork(session),
        policy=AnalyticsRuntimePolicy(
            page_token_secret="income-pg-test",
            page_token_key_id="test",
            page_token_previous_keys={},
            page_token_ttl_seconds=900,
            export_stale_timeout_minutes=15,
            export_execution_timeout_seconds=300,
        ),
    )
    window = AnalyticsWindow(start_date=INCOME_PRIOR_DAY, end_date=ACQUISITION_DAY)
    for zone in ("UTC", "Asia/Singapore", "America/Los_Angeles"):
        await session.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone})
        positions = await service.get_position_timeseries(
            portfolio_id=PORTFOLIO,
            request=PositionAnalyticsTimeseriesRequest(
                as_of_date=ACQUISITION_DAY,
                window=window,
                dimensions=["asset_class"],
            ),
        )
        cash = next(
            row
            for row in positions.rows
            if row.valuation_date == INCOME_DAY and row.security_id == "CASH"
        )
        bond = next(
            row
            for row in positions.rows
            if row.valuation_date == INCOME_DAY and row.security_id == "BOND"
        )
        assert (
            cash.beginning_market_value_reporting_currency,
            cash.ending_market_value_reporting_currency,
        ) == (Decimal("100"), Decimal("110"))
        assert [(flow.amount, flow.flow_scope) for flow in cash.cash_flows] == [
            (Decimal("10"), "internal")
        ]
        assert [(flow.amount, flow.cash_flow_type) for flow in bond.cash_flows] == [
            (Decimal("-10"), "income")
        ]
        acquired = next(
            row
            for row in positions.rows
            if row.valuation_date == ACQUISITION_DAY and row.security_id == "EQUITY"
        )
        acquired_cash = next(
            row
            for row in positions.rows
            if row.valuation_date == ACQUISITION_DAY and row.security_id == "CASH"
        )
        assert (
            acquired.beginning_market_value_reporting_currency,
            acquired.ending_market_value_reporting_currency,
        ) == (Decimal("0"), Decimal("49"))
        assert [(flow.amount, flow.flow_scope) for flow in acquired.cash_flows] == [
            (Decimal("50"), "internal")
        ]
        assert (
            acquired_cash.beginning_market_value_reporting_currency,
            acquired_cash.ending_market_value_reporting_currency,
        ) == (Decimal("110"), Decimal("60"))
        assert [(flow.amount, flow.flow_scope) for flow in acquired_cash.cash_flows] == [
            (Decimal("-50"), "internal")
        ]
        portfolio = await service.get_portfolio_timeseries(
            portfolio_id=PORTFOLIO,
            request=PortfolioAnalyticsTimeseriesRequest(as_of_date=ACQUISITION_DAY, window=window),
        )
        income = next(row for row in portfolio.observations if row.valuation_date == INCOME_DAY)
        assert (income.beginning_market_value, income.ending_market_value) == (
            Decimal("500"),
            Decimal("514"),
        )
        assert income.cash_flows == []
        acquisition = next(
            row for row in portfolio.observations if row.valuation_date == ACQUISITION_DAY
        )
        assert (acquisition.beginning_market_value, acquisition.ending_market_value) == (
            Decimal("514"),
            Decimal("515"),
        )
        assert acquisition.cash_flows == []
        # Independent capital attribution: cash 0 + bond mark 2 - equity
        # acquisition slippage 1 equals the portfolio's 1 unit gain.
        assert (Decimal("60") - Decimal("110") + Decimal("50")) + (
            Decimal("406") - Decimal("404")
        ) + (Decimal("49") - Decimal("50")) == Decimal("1")
        await session.commit()


async def test_trade_date_position_flows_preserve_settlement_and_replay_truth(
    clean_db, async_db_session: AsyncSession
) -> None:
    session = async_db_session
    session.add(
        Portfolio(
            tenant_id="tenant-trade-date-analytics",
            portfolio_id=PORTFOLIO,
            base_currency="USD",
            open_date=TRADE_DAY,
            risk_exposure="moderate",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="Singapore",
            client_id="CLIENT_TRADE_DATE_ANALYTICS",
            status="ACTIVE",
        )
    )
    await session.flush()
    session.add_all(
        [
            _transaction("BUY-EQUITY", "EQUITY", "BUY"),
            _transaction("SELL-CASH", "CASH", "SELL"),
            _transaction("EXTERNAL-DEPOSIT", "CASH", "DEPOSIT"),
        ]
    )
    await session.flush()
    session.add_all(
        [
            PositionHistory(
                portfolio_id=PORTFOLIO,
                security_id=security_id,
                transaction_id=transaction_id,
                position_date=TRADE_DAY,
                epoch=0,
                quantity=Decimal("1"),
                cost_basis=Decimal("100"),
                cost_basis_local=Decimal("100"),
            )
            for transaction_id, security_id in (
                ("BUY-EQUITY", "EQUITY"),
                ("SELL-CASH", "CASH"),
            )
        ]
    )
    session.add_all(
        [
            _cashflow(
                "BUY-EQUITY",
                "EQUITY",
                flow_date=SETTLEMENT_DAY,
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                amount="-100",
            ),
            _cashflow(
                "SELL-CASH",
                "CASH",
                flow_date=SETTLEMENT_DAY,
                classification="INVESTMENT_INFLOW",
                timing="EOD",
                amount="100",
            ),
            _cashflow(
                "EXTERNAL-DEPOSIT",
                "CASH",
                flow_date=TRADE_DAY,
                classification="CASHFLOW_IN",
                timing="BOD",
                amount="50",
                portfolio_flow=True,
            ),
            # A later replay moves the external source date out of the trade-day
            # selection. Ranking after a date predicate would resurrect epoch 0.
            _cashflow(
                "EXTERNAL-DEPOSIT",
                "CASH",
                flow_date=DEPOSIT_DAY,
                classification="CASHFLOW_IN",
                timing="BOD",
                amount="55",
                epoch=1,
                portfolio_flow=True,
            ),
        ]
    )
    await session.commit()

    reader = analytics_timeseries_repository.AnalyticsTimeseriesRepository(session)
    for zone in ("UTC", "Asia/Singapore", "America/Los_Angeles"):
        await session.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone})
        trade_rows = await reader.list_position_cashflow_rows(
            portfolio_id=PORTFOLIO,
            security_ids=["EQUITY", "CASH"],
            valuation_dates=[TRADE_DAY],
            snapshot_epoch=1,
        )
        assert {(row.transaction_id, row.valuation_date, row.amount) for row in trade_rows} == {
            ("BUY-EQUITY", TRADE_DAY, Decimal("-100")),
            ("SELL-CASH", TRADE_DAY, Decimal("100")),
        }
        assert (
            await reader.list_position_cashflow_rows(
                portfolio_id=PORTFOLIO,
                security_ids=["EQUITY", "CASH"],
                valuation_dates=[SETTLEMENT_DAY],
                snapshot_epoch=1,
            )
            == []
        )
        deposit_rows = await reader.list_position_cashflow_rows(
            portfolio_id=PORTFOLIO,
            security_ids=["CASH"],
            valuation_dates=[DEPOSIT_DAY],
            snapshot_epoch=1,
        )
        assert [(row.transaction_id, row.amount) for row in deposit_rows] == [
            ("EXTERNAL-DEPOSIT", Decimal("55"))
        ]
        assert (
            await reader.list_portfolio_cashflow_rows(
                portfolio_id=PORTFOLIO,
                valuation_dates=[TRADE_DAY],
                snapshot_epoch=1,
            )
            == []
        )
        assert [
            row.amount
            for row in await reader.list_portfolio_cashflow_rows(
                portfolio_id=PORTFOLIO,
                valuation_dates=[DEPOSIT_DAY],
                snapshot_epoch=1,
            )
        ] == [Decimal("55")]
        await session.commit()  # release connection; next zone uses a fresh session

    old_epoch_rows = await reader.list_position_cashflow_rows(
        portfolio_id=PORTFOLIO,
        security_ids=["CASH"],
        valuation_dates=[TRADE_DAY],
        snapshot_epoch=0,
    )
    assert {row.transaction_id for row in old_epoch_rows} == {"SELL-CASH", "EXTERNAL-DEPOSIT"}

    # A correction updates the mutable transaction before the next cashflow
    # epoch is processed. A prior snapshot must retain its own trade date.
    await session.execute(
        update(Transaction)
        .where(Transaction.transaction_id == "BUY-EQUITY")
        .values(transaction_date=datetime(2026, 4, 14, 0, 30, tzinfo=UTC))
    )
    await session.commit()
    old_trade_rows = await reader.list_position_cashflow_rows(
        portfolio_id=PORTFOLIO,
        security_ids=["EQUITY"],
        valuation_dates=[TRADE_DAY],
        snapshot_epoch=0,
    )
    assert [(row.transaction_id, row.valuation_date) for row in old_trade_rows] == [
        ("BUY-EQUITY", TRADE_DAY)
    ]

    # A newer durable epoch moves the trade-day recognition, while the old
    # cursor still returns its original result.
    session.add(
        PositionHistory(
            portfolio_id=PORTFOLIO,
            security_id="EQUITY",
            transaction_id="BUY-EQUITY",
            position_date=date(2026, 4, 14),
            epoch=1,
            quantity=Decimal("1"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
        )
    )
    session.add(
        _cashflow(
            "BUY-EQUITY",
            "EQUITY",
            flow_date=SETTLEMENT_DAY,
            classification="INVESTMENT_OUTFLOW",
            timing="BOD",
            amount="-100",
            epoch=1,
        )
    )
    await session.commit()
    assert [
        row.transaction_id
        for row in await reader.list_position_cashflow_rows(
            portfolio_id=PORTFOLIO,
            security_ids=["EQUITY"],
            valuation_dates=[date(2026, 4, 14)],
            snapshot_epoch=1,
        )
    ] == ["BUY-EQUITY"]
    assert (
        await reader.list_position_cashflow_rows(
            portfolio_id=PORTFOLIO,
            security_ids=["EQUITY"],
            valuation_dates=[TRADE_DAY],
            snapshot_epoch=1,
        )
        == []
    )
    assert [
        row.transaction_id
        for row in await reader.list_position_cashflow_rows(
            portfolio_id=PORTFOLIO,
            security_ids=["EQUITY"],
            valuation_dates=[TRADE_DAY],
            snapshot_epoch=0,
        )
    ] == ["BUY-EQUITY"]

    await session.execute(
        delete(PositionHistory).where(
            PositionHistory.transaction_id == "BUY-EQUITY",
            PositionHistory.epoch == 0,
        )
    )
    await session.commit()
    with pytest.raises(AnalyticsCashflowEpochEvidenceError):
        await reader.list_position_cashflow_rows(
            portfolio_id=PORTFOLIO,
            security_ids=["EQUITY"],
            valuation_dates=[TRADE_DAY],
            snapshot_epoch=0,
        )
