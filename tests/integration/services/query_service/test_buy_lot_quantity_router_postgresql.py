"""Exact persisted BUY quantities through the registered in-process HTTP route."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from portfolio_common.database_models import Portfolio, PositionLotState, Transaction
from portfolio_common.db import get_async_db_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.main import app
from src.services.query_service.app.repositories.buy_state_repository import BuyStateRepository
from tests.test_support.tenant import TEST_LEGAL_BOOK_ID, TEST_TENANT_HEADERS, TEST_TENANT_ID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

QUANTITIES = (
    "100.0000000000",
    "0.1234567890",
    "0.0000000001",
    "12345678.1234567890",
    "99999999.9999999998",
    "99999999.9999999999",
    "0.0000000000",
)
PORTFOLIO_ID = "EXACT-LOT-PG"
SECURITY_ID = "EXACT-SEC-PG"


async def _seed_lots(session: AsyncSession) -> None:
    for portfolio_id, tenant_id in (
        (PORTFOLIO_ID, TEST_TENANT_ID),
        ("EXACT-LOT-FOREIGN-PG", "FOREIGN-TENANT"),
    ):
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                tenant_id=tenant_id,
                legal_book_id=TEST_LEGAL_BOOK_ID,
                base_currency="USD",
                open_date=date(2026, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                objective="CAPITAL_GROWTH",
                booking_center_code="SG",
                client_id="EXACT-CLIENT-PG",
                status="ACTIVE",
                is_leverage_allowed=False,
            )
        )
    await session.flush()
    for index, quantity in enumerate(QUANTITIES):
        transaction_id = f"EXACT-TXN-{index}"
        session.add(
            Transaction(
                transaction_id=transaction_id,
                portfolio_id=PORTFOLIO_ID,
                instrument_id=SECURITY_ID,
                security_id=SECURITY_ID,
                transaction_type="BUY",
                quantity=Decimal(quantity),
                price=Decimal("1"),
                gross_transaction_amount=Decimal(quantity),
                trade_currency="USD",
                currency="USD",
                transaction_date=datetime(2026, 2, 28, tzinfo=UTC),
            )
        )
        await session.flush()
        session.add(
            PositionLotState(
                lot_id=f"EXACT-LOT-{index}",
                source_transaction_id=transaction_id,
                portfolio_id=PORTFOLIO_ID,
                instrument_id=SECURITY_ID,
                security_id=SECURITY_ID,
                acquisition_date=date(2026, 2, 28),
                original_quantity=Decimal(quantity),
                open_quantity=Decimal(quantity) if index != 0 else Decimal("0"),
                lot_cost_local=Decimal("15005.1234567890"),
                lot_cost_base=Decimal("17005.9876543210"),
                accrued_interest_paid_local=Decimal("0.0000000000"),
                economic_event_id="EXACT-EVT",
                linked_transaction_group_id="EXACT-LTG",
                calculation_policy_id="BUY_DEFAULT_POLICY",
                calculation_policy_version="1.0.0",
                source_system="SYNTHETIC_TEST",
            )
        )
    await session.commit()
    session.expunge_all()


async def test_registered_lots_preserve_postgresql_exact_quantities(
    clean_db,
    async_db_session: AsyncSession,
):
    await _seed_lots(async_db_session)
    stored = list(
        (await async_db_session.execute(select(PositionLotState).order_by(PositionLotState.id)))
        .scalars()
        .all()
    )
    assert [lot.original_quantity for lot in stored] == [Decimal(q) for q in QUANTITIES]
    assert stored[4].original_quantity != stored[5].original_quantity
    async_db_session.expunge_all()

    async def override_db():
        yield async_db_session

    app.dependency_overrides[get_async_db_session] = override_db
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers=TEST_TENANT_HEADERS,
        ) as client:
            response = await client.get(f"/portfolios/{PORTFOLIO_ID}/positions/{SECURITY_ID}/lots")
            assert response.status_code == 200
            lots = response.json()["lots"]
            assert len(lots) == len(stored)
            assert [Decimal(str(lot["original_quantity"])) for lot in lots] == [
                lot.original_quantity for lot in stored
            ]
            assert [Decimal(str(lot["open_quantity"])) for lot in lots] == [
                lot.open_quantity for lot in stored
            ]
            for actual, source in zip(lots, stored, strict=True):
                for field in ("original_quantity", "open_quantity"):
                    # Decimal(str(...)) also detects numeric loss on the pre-fix DTO.
                    assert Decimal(str(actual[field])) == getattr(source, field)
                    assert isinstance(actual[field], str)
                for field in ("lot_cost_local", "lot_cost_base", "accrued_interest_paid_local"):
                    assert Decimal(actual[field]) == getattr(source, field)
                for field in (
                    "lot_id",
                    "source_transaction_id",
                    "portfolio_id",
                    "instrument_id",
                    "security_id",
                    "economic_event_id",
                    "linked_transaction_group_id",
                    "calculation_policy_id",
                    "calculation_policy_version",
                    "source_system",
                ):
                    assert actual[field] == getattr(source, field)
                assert actual["acquisition_date"] == source.acquisition_date.isoformat()
            assert lots[4]["original_quantity"] != lots[5]["original_quantity"]
            assert lots[4]["open_quantity"] != lots[5]["open_quantity"]
            assert Decimal(lots[0]["open_quantity"]) == 0  # closed lot remains visible
            empty = await client.get(f"/portfolios/{PORTFOLIO_ID}/positions/EMPTY-SEC/lots")
            assert empty.status_code == 404
            with patch.object(
                BuyStateRepository, "get_position_lots", new_callable=AsyncMock
            ) as read:
                foreign = await client.get(
                    f"/portfolios/EXACT-LOT-FOREIGN-PG/positions/{SECURITY_ID}/lots"
                )
                assert foreign.status_code == 404
                read.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_async_db_session, None)
