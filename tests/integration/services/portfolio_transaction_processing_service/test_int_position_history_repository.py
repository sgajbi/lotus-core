"""Verify live position-history repository queries against PostgreSQL."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Portfolio,
    PositionHistory,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.portfolio_transaction_processing_service.app.infrastructure.sqlalchemy_position_history_repository import (  # noqa: E501
    SqlAlchemyPositionHistoryRepository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

PORTFOLIO_ID = "POSITION_HISTORY_REPOSITORY_01"
SECURITY_ID = "SEC_POSITION_HISTORY_01"


@pytest.fixture(scope="function")
def position_history_repository_data(db_engine) -> None:
    """Seed independently versioned snapshot and history epochs."""
    with Session(db_engine) as session:
        portfolio = Portfolio(
            portfolio_id=PORTFOLIO_ID,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="ACTIVE",
        )
        session.add(portfolio)
        session.flush()
        session.add_all(
            [
                DailyPositionSnapshot(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    date=date(2025, 8, 1),
                    epoch=0,
                    quantity=Decimal("1"),
                    cost_basis=Decimal("1"),
                ),
                DailyPositionSnapshot(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    date=date(2025, 8, 5),
                    epoch=0,
                    quantity=Decimal("1"),
                    cost_basis=Decimal("1"),
                ),
                DailyPositionSnapshot(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    date=date(2025, 8, 10),
                    epoch=1,
                    quantity=Decimal("1"),
                    cost_basis=Decimal("1"),
                ),
            ]
        )
        transactions = [
            Transaction(
                transaction_id="TX_POSITION_HISTORY_E0_A",
                portfolio_id=PORTFOLIO_ID,
                instrument_id=SECURITY_ID,
                security_id=SECURITY_ID,
                transaction_date=date(2025, 8, 1),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
            Transaction(
                transaction_id="TX_POSITION_HISTORY_E0_B",
                portfolio_id=PORTFOLIO_ID,
                instrument_id=SECURITY_ID,
                security_id=SECURITY_ID,
                transaction_date=date(2025, 8, 6),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
            Transaction(
                transaction_id="TX_POSITION_HISTORY_E1_A",
                portfolio_id=PORTFOLIO_ID,
                instrument_id=SECURITY_ID,
                security_id=SECURITY_ID,
                transaction_date=date(2025, 8, 9),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
        ]
        session.add_all(transactions)
        session.flush()
        session.add_all(
            [
                PositionHistory(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    transaction_id="TX_POSITION_HISTORY_E0_A",
                    position_date=date(2025, 8, 1),
                    quantity=Decimal("1"),
                    cost_basis=Decimal("1"),
                    epoch=0,
                ),
                PositionHistory(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    transaction_id="TX_POSITION_HISTORY_E0_B",
                    position_date=date(2025, 8, 6),
                    quantity=Decimal("2"),
                    cost_basis=Decimal("2"),
                    epoch=0,
                ),
                PositionHistory(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    transaction_id="TX_POSITION_HISTORY_E1_A",
                    position_date=date(2025, 8, 9),
                    quantity=Decimal("3"),
                    cost_basis=Decimal("3"),
                    epoch=1,
                ),
            ]
        )
        session.commit()


async def test_latest_completed_snapshot_date_is_epoch_scoped(
    clean_db,
    position_history_repository_data: None,
    async_db_session: AsyncSession,
) -> None:
    del clean_db, position_history_repository_data
    repository = SqlAlchemyPositionHistoryRepository(async_db_session)

    assert await repository.latest_completed_snapshot_date(
        portfolio_id=f" {PORTFOLIO_ID} ", security_id=f" {SECURITY_ID} ", epoch=0
    ) == date(2025, 8, 5)
    assert await repository.latest_completed_snapshot_date(
        portfolio_id=PORTFOLIO_ID, security_id=SECURITY_ID, epoch=1
    ) == date(2025, 8, 10)
    assert (
        await repository.latest_completed_snapshot_date(
            portfolio_id=PORTFOLIO_ID, security_id=SECURITY_ID, epoch=2
        )
        is None
    )


async def test_latest_history_date_is_epoch_scoped(
    clean_db,
    position_history_repository_data: None,
    async_db_session: AsyncSession,
) -> None:
    del clean_db, position_history_repository_data
    repository = SqlAlchemyPositionHistoryRepository(async_db_session)

    assert await repository.latest_history_date(
        portfolio_id=f" {PORTFOLIO_ID} ", security_id=f" {SECURITY_ID} ", epoch=0
    ) == date(2025, 8, 6)
    assert await repository.latest_history_date(
        portfolio_id=PORTFOLIO_ID, security_id=SECURITY_ID, epoch=1
    ) == date(2025, 8, 9)
    assert (
        await repository.latest_history_date(
            portfolio_id=PORTFOLIO_ID, security_id=SECURITY_ID, epoch=2
        )
        is None
    )
