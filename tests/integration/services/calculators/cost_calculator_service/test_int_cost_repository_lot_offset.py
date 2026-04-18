from datetime import date, datetime
from decimal import Decimal

import pytest
from cost_engine.domain.models.transaction import (
    Transaction as EngineTransaction,
)
from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    Portfolio,
    PositionLotState,
)
from portfolio_common.database_models import (
    Transaction as DBTransaction,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cost_calculator_service.app.repository import (
    CostCalculatorRepository,
)

pytestmark = pytest.mark.asyncio


async def test_cost_repository_persists_buy_lot_and_offset_state(
    clean_db, async_db_session: AsyncSession
) -> None:
    lot_table_exists = await async_db_session.scalar(
        text("SELECT to_regclass('public.position_lot_state')")
    )
    offset_table_exists = await async_db_session.scalar(
        text("SELECT to_regclass('public.accrued_income_offset_state')")
    )
    assert lot_table_exists, "position_lot_state table is required in the active test schema."
    assert (
        offset_table_exists
    ), "accrued_income_offset_state table is required in the active test schema."

    async_db_session.add(
        Portfolio(
            portfolio_id="PORT_SLICE4_01",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="Medium",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CIF_SLICE4_01",
            status="ACTIVE",
        )
    )
    async_db_session.add(
        DBTransaction(
            transaction_id="TXN_SLICE4_01",
            portfolio_id="PORT_SLICE4_01",
            instrument_id="BOND_USD_01",
            security_id="BOND_USD_01",
            transaction_type="BUY",
            quantity=Decimal("100"),
            price=Decimal("98"),
            gross_transaction_amount=Decimal("9800"),
            trade_currency="USD",
            currency="USD",
            transaction_date=datetime(2026, 2, 28, 10, 0, 0),
        )
    )
    await async_db_session.commit()

    repo = CostCalculatorRepository(async_db_session)
    txn = EngineTransaction(
        transaction_id="TXN_SLICE4_01",
        portfolio_id="PORT_SLICE4_01",
        instrument_id="BOND_USD_01",
        security_id="BOND_USD_01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 2, 28, 10, 0, 0),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("9800"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost_local=Decimal("9840"),
        net_cost=Decimal("9840"),
        accrued_interest=Decimal("125"),
        economic_event_id="EVT-2026-777",
        linked_transaction_group_id="LTG-2026-777",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        source_system="OMS_PRIMARY",
    )

    await repo.upsert_buy_lot_state(txn)
    await repo.upsert_accrued_income_offset_state(txn)
    await async_db_session.commit()

    lot_stmt = select(PositionLotState).where(
        PositionLotState.source_transaction_id == "TXN_SLICE4_01"
    )
    lot = (await async_db_session.execute(lot_stmt)).scalar_one()
    assert lot.original_quantity == Decimal("100")
    assert lot.open_quantity == Decimal("100")
    assert lot.lot_cost_local == Decimal("9840")
    assert lot.accrued_interest_paid_local == Decimal("125")
    assert lot.economic_event_id == "EVT-2026-777"

    offset_stmt = select(AccruedIncomeOffsetState).where(
        AccruedIncomeOffsetState.source_transaction_id == "TXN_SLICE4_01"
    )
    offset = (await async_db_session.execute(offset_stmt)).scalar_one()
    assert offset.accrued_interest_paid_local == Decimal("125")
    assert offset.remaining_offset_local == Decimal("125")
    assert offset.linked_transaction_group_id == "LTG-2026-777"


async def test_cost_repository_updates_lot_open_quantity_from_engine_state(
    clean_db, async_db_session: AsyncSession
) -> None:
    async_db_session.add(
        Portfolio(
            portfolio_id="PORT_SLICE4_02",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="Medium",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CIF_SLICE4_02",
            status="ACTIVE",
        )
    )
    async_db_session.add(
        DBTransaction(
            transaction_id="TXN_SLICE4_02",
            portfolio_id="PORT_SLICE4_02",
            instrument_id="BOND_USD_02",
            security_id="BOND_USD_02",
            transaction_type="BUY",
            quantity=Decimal("100"),
            price=Decimal("98"),
            gross_transaction_amount=Decimal("9800"),
            trade_currency="USD",
            currency="USD",
            transaction_date=datetime(2026, 2, 28, 10, 0, 0),
        )
    )
    await async_db_session.commit()

    async_db_session.add(
        PositionLotState(
            lot_id="LOT-TXN_SLICE4_02",
            source_transaction_id="TXN_SLICE4_02",
            portfolio_id="PORT_SLICE4_02",
            instrument_id="BOND_USD_02",
            security_id="BOND_USD_02",
            acquisition_date=date(2026, 2, 28),
            original_quantity=Decimal("100"),
            open_quantity=Decimal("100"),
            lot_cost_local=Decimal("9800"),
            lot_cost_base=Decimal("9800"),
        )
    )
    await async_db_session.commit()

    repo = CostCalculatorRepository(async_db_session)
    await repo.update_lot_open_quantities(
        portfolio_id="PORT_SLICE4_02",
        security_id="BOND_USD_02",
        open_quantities_by_source_transaction_id={"TXN_SLICE4_02": Decimal("40")},
    )
    await async_db_session.commit()

    lot_stmt = select(PositionLotState).where(
        PositionLotState.source_transaction_id == "TXN_SLICE4_02"
    )
    lot = (await async_db_session.execute(lot_stmt)).scalar_one()
    assert lot.open_quantity == Decimal("40")
