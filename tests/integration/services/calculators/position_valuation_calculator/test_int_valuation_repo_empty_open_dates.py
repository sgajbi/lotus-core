from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from portfolio_common.database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    Portfolio,
    PositionState,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_find_contiguous_snapshot_dates_handles_empty_first_open_dates(
    clean_db, async_db_session: AsyncSession
):
    valuation_repository_module = import_module(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository"
    )
    ValuationRepository = valuation_repository_module.ValuationRepository
    repo = ValuationRepository(async_db_session)

    async_db_session.add(
        Portfolio(
            portfolio_id="P-EMPTY-OPEN-DATES",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="ACTIVE",
        )
    )
    await async_db_session.commit()

    async_db_session.add(
        Transaction(
            transaction_id="TX-EMPTY-OPEN-DATES-1",
            portfolio_id="P-EMPTY-OPEN-DATES",
            instrument_id="I-EMPTY-OPEN-DATES",
            security_id="S-EMPTY-OPEN-DATES",
            transaction_date=date(2025, 8, 10),
            transaction_type="BUY",
            quantity=1,
            price=1,
            gross_transaction_amount=1,
            trade_currency="USD",
            currency="USD",
        )
    )
    await async_db_session.commit()

    async_db_session.add_all(
        [
            PositionState(
                portfolio_id="P-EMPTY-OPEN-DATES",
                security_id="S-EMPTY-OPEN-DATES",
                epoch=0,
                watermark_date=date(2025, 8, 10),
                status="CURRENT",
            ),
            BusinessDate(calendar_code="GLOBAL", date=date(2025, 8, 10)),
            BusinessDate(calendar_code="GLOBAL", date=date(2025, 8, 11)),
            DailyPositionSnapshot(
                portfolio_id="P-EMPTY-OPEN-DATES",
                security_id="S-EMPTY-OPEN-DATES",
                date=date(2025, 8, 10),
                epoch=0,
                quantity=Decimal("10"),
                cost_basis=Decimal("100"),
                cost_basis_local=Decimal("100"),
                market_price=Decimal("10"),
                market_value=Decimal("100"),
                market_value_local=Decimal("100"),
                unrealized_gain_loss=Decimal("0"),
                unrealized_gain_loss_local=Decimal("0"),
                valuation_status="VALUED_CURRENT",
            ),
        ]
    )
    await async_db_session.commit()

    states = [
        PositionState(
            portfolio_id="P-EMPTY-OPEN-DATES",
            security_id="S-EMPTY-OPEN-DATES",
            epoch=0,
            watermark_date=date(2025, 8, 10),
            status="CURRENT",
        )
    ]

    contiguous_dates = await repo.find_contiguous_snapshot_dates(states, {})

    assert contiguous_dates == {
        ("P-EMPTY-OPEN-DATES", "S-EMPTY-OPEN-DATES"): date(2025, 8, 10)
    }
