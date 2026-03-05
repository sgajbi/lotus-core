# tests/integration/services/calculators/position_calculator/test_int_reprocessing_atomicity.py
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    Portfolio,
    PositionState,
)
from portfolio_common.database_models import (
    Transaction as DBTransaction,
)
from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.repositories.position_repository import (
    PositionRepository,
)

pytestmark = pytest.mark.asyncio

PORTFOLIO_ID = "E2E_REPRO_ATOM_01"
SECURITY_ID = "SEC_REPRO_ATOM_01"


@pytest_asyncio.fixture(scope="function")
async def setup_repro_atomicity_data(async_db_session: AsyncSession):
    """Sets up the initial state for the atomicity test."""
    # Clean up before test
    await async_db_session.execute(
        text(
            """
            TRUNCATE TABLE
                outbox_events,
                daily_position_snapshots,
                position_history,
                position_timeseries,
                portfolio_timeseries,
                position_state,
                transactions,
                portfolios
            RESTART IDENTITY CASCADE
            """
        )
    )

    # ARRANGE: Create initial state
    async_db_session.add(
        Portfolio(
            portfolio_id=PORTFOLIO_ID,
            base_currency="USD",
            open_date=date(2025, 1, 1),
            client_id="ATOM_CIF",
            status="ACTIVE",
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
        )
    )

    async_db_session.add(
        PositionState(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            watermark_date=date(2025, 9, 9),
            epoch=0,
            status="CURRENT",
        )
    )

    async_db_session.add(
        DBTransaction(
            transaction_id="TXN_ATOM_CURRENT",
            portfolio_id=PORTFOLIO_ID,
            instrument_id="ATS",
            security_id=SECURITY_ID,
            transaction_date=datetime(2025, 9, 10, 10, tzinfo=timezone.utc),
            transaction_type="BUY",
            quantity=100,
            price=10,
            gross_transaction_amount=1000,
            trade_currency="USD",
            currency="USD",
        )
    )
    await async_db_session.commit()


async def test_reprocessing_is_atomic_on_outbox_failure(
    setup_repro_atomicity_data, async_db_session: AsyncSession
):
    """
    This test verifies the new atomic implementation.
    It simulates a crash during the outbox creation step and asserts that
    the entire database transaction is rolled back, leaving the system in a
    consistent state.
    """
    # The pytest-asyncio fixture is automatically awaited, no need to await it here.

    # ARRANGE: Instantiate real repositories and a failing OutboxRepository
    repo = PositionRepository(async_db_session)
    position_state_repo = PositionStateRepository(async_db_session)
    outbox_repo = OutboxRepository(async_db_session)

    # Mock the outbox repo to fail, simulating a DB constraint violation or other error
    outbox_repo.create_outbox_event = AsyncMock(side_effect=Exception("Outbox failed!"))

    back_dated_event = TransactionEvent(
        transaction_id="TXN_ATOM_BACKDATED",
        portfolio_id=PORTFOLIO_ID,
        instrument_id="ATS",
        security_id=SECURITY_ID,
        transaction_date=datetime(2025, 9, 5, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=10,
        price=9,
        gross_transaction_amount=90,
        trade_currency="USD",
        currency="USD",
        epoch=None,  # An original event has no epoch
    )

    # ACT: Attempt to process the back-dated event, which should fail
    with pytest.raises(Exception, match="Outbox failed!"):
        await PositionCalculator.calculate(
            event=back_dated_event,
            db_session=async_db_session,
            repo=repo,
            position_state_repo=position_state_repo,
            outbox_repo=outbox_repo,
        )

    # ASSERT: Verify that the transaction was rolled back
    # The session is now in a failed state, so we need a new one to query
    from sqlalchemy.orm import sessionmaker

    async_session_maker = sessionmaker(
        async_db_session.bind, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as new_session:
        # 1. The position_state should NOT have been updated to epoch 1
        state_result = await new_session.execute(
            text(
                "SELECT epoch, status FROM position_state WHERE portfolio_id = :pid AND security_id = :sid"  # noqa: E501
            ),
            {"pid": PORTFOLIO_ID, "sid": SECURITY_ID},
        )
        final_state = state_result.fetchone()
        assert final_state.epoch == 0
        assert final_state.status == "CURRENT"

        # 2. No outbox events should have been created
        outbox_result = await new_session.execute(text("SELECT COUNT(*) FROM outbox_events"))
        assert outbox_result.scalar_one() == 0
