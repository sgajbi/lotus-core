"""Trade-date position analytics must not inherit settlement-ledger chronology."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import Cashflow, Portfolio, PositionHistory, Transaction
from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.domain.analytics import (
    AnalyticsCashflowEpochEvidenceError,
)
from src.services.query_control_plane_service.app.infrastructure import (
    analytics_timeseries_repository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct, pytest.mark.lifecycle]

PORTFOLIO = "TRADE_DATE_ANALYTICS_PG"
TRADE_DAY = date(2026, 4, 10)
SETTLEMENT_DAY = date(2026, 4, 12)
DEPOSIT_DAY = date(2026, 4, 13)


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
