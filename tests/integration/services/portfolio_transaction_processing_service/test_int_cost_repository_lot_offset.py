from datetime import date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    Portfolio,
    PositionLotState,
    TransactionCost,
)
from portfolio_common.database_models import (
    Transaction as DBTransaction,
)
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    Fees,
    OpenLotState,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisLotRepository,
    SqlAlchemyCostBasisTransactionRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.income import (
    SqlAlchemyAccruedIncomeOffsetRepository,
)

pytestmark = pytest.mark.asyncio


async def _persist_cost_state_parent(
    session: AsyncSession,
    *,
    suffix: str,
) -> tuple[str, str]:
    portfolio_id = f"PORT_COST_CONSTRAINT_{suffix}"
    transaction_id = f"TXN_COST_CONSTRAINT_{suffix}"
    session.add(
        Portfolio(
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="Medium",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id=f"CIF_COST_CONSTRAINT_{suffix}",
            status="ACTIVE",
        )
    )
    session.add(
        DBTransaction(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=f"BOND_{suffix}",
            security_id=f"BOND_{suffix}",
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            trade_currency="USD",
            currency="USD",
            transaction_date=datetime(2026, 4, 10, 10, 0, 0),
        )
    )
    await session.commit()
    return portfolio_id, transaction_id


@pytest.mark.parametrize(
    ("overrides", "constraint_name"),
    [
        (
            {"open_quantity": Decimal("-1")},
            "ck_position_lot_open_quantity_nonnegative",
        ),
        (
            {"original_quantity": Decimal("1"), "open_quantity": Decimal("2")},
            "ck_position_lot_open_not_above_original",
        ),
        (
            {"lot_cost_local": Decimal("-1")},
            "ck_position_lot_local_cost_nonnegative",
        ),
        (
            {"lot_cost_base": Decimal("-1")},
            "ck_position_lot_base_cost_nonnegative",
        ),
    ],
)
async def test_position_lot_database_rejects_invalid_ledger_state(
    clean_db,
    async_db_session: AsyncSession,
    overrides: dict[str, Decimal],
    constraint_name: str,
) -> None:
    suffix = constraint_name.removeprefix("ck_position_lot_").upper()
    portfolio_id, transaction_id = await _persist_cost_state_parent(
        async_db_session,
        suffix=suffix,
    )
    values = {
        "lot_id": f"LOT-{transaction_id}",
        "source_transaction_id": transaction_id,
        "portfolio_id": portfolio_id,
        "instrument_id": f"BOND_{suffix}",
        "security_id": f"BOND_{suffix}",
        "acquisition_date": date(2026, 4, 10),
        "original_quantity": Decimal("1"),
        "open_quantity": Decimal("1"),
        "lot_cost_local": Decimal("1"),
        "lot_cost_base": Decimal("1"),
        "accrued_interest_paid_local": Decimal("0"),
    }
    values.update(overrides)
    async_db_session.add(PositionLotState(**values))

    with pytest.raises(IntegrityError, match=constraint_name):
        await async_db_session.commit()
    await async_db_session.rollback()


async def test_transaction_cost_database_rejects_nonpositive_component(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    _, transaction_id = await _persist_cost_state_parent(
        async_db_session,
        suffix="NONPOSITIVE_FEE",
    )
    async_db_session.add(
        TransactionCost(
            transaction_id=transaction_id,
            fee_type="broker_commission",
            amount=Decimal("0"),
            currency="USD",
        )
    )

    with pytest.raises(IntegrityError, match="ck_transaction_costs_amount_positive"):
        await async_db_session.commit()
    await async_db_session.rollback()


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
    assert offset_table_exists, (
        "accrued_income_offset_state table is required in the active test schema."
    )

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

    lot_repo = SqlAlchemyCostBasisLotRepository(async_db_session)
    income_offset_repo = SqlAlchemyAccruedIncomeOffsetRepository(async_db_session)
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

    await lot_repo.upsert_buy_lot_state(txn)
    await income_offset_repo.upsert_accrued_income_offset(txn)
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


async def test_cost_repository_updates_current_lot_quantity_and_cost_from_engine_state(
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

    lot_repo = SqlAlchemyCostBasisLotRepository(async_db_session)
    await lot_repo.update_open_lot_states(
        portfolio_id="PORT_SLICE4_02",
        security_id="BOND_USD_02",
        states_by_source_transaction_id={
            "TXN_SLICE4_02": OpenLotState(
                quantity=Decimal("40"),
                cost_local=Decimal("3920"),
                cost_base=Decimal("4000"),
            )
        },
    )
    await async_db_session.commit()

    lot_stmt = select(PositionLotState).where(
        PositionLotState.source_transaction_id == "TXN_SLICE4_02"
    )
    lot = (await async_db_session.execute(lot_stmt)).scalar_one()
    assert lot.open_quantity == Decimal("40")
    assert lot.lot_cost_local == Decimal("3920")
    assert lot.lot_cost_base == Decimal("4000")


async def test_fifo_disposal_reads_and_updates_only_required_open_lots(
    clean_db, async_db_session: AsyncSession
) -> None:
    portfolio_id = "PORT_FIFO_BOUNDED_01"
    security_id = "EQ_FIFO_BOUNDED_01"
    async_db_session.add(
        Portfolio(
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="Medium",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CIF_FIFO_BOUNDED_01",
            status="ACTIVE",
        )
    )
    lot_inputs = (
        ("BUY_FIFO_01", datetime(2026, 1, 1, 10, 0, 0), Decimal("4")),
        ("BUY_FIFO_02", datetime(2026, 1, 2, 10, 0, 0), Decimal("5")),
        ("BUY_FIFO_03", datetime(2026, 1, 3, 10, 0, 0), Decimal("7")),
    )
    for transaction_id, transaction_date, quantity in lot_inputs:
        async_db_session.add(
            DBTransaction(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                instrument_id=security_id,
                security_id=security_id,
                transaction_type="BUY",
                quantity=quantity,
                price=Decimal("100"),
                gross_transaction_amount=quantity * Decimal("100"),
                trade_currency="USD",
                currency="USD",
                transaction_date=transaction_date,
            )
        )
    await async_db_session.commit()

    for transaction_id, transaction_date, quantity in lot_inputs:
        async_db_session.add(
            PositionLotState(
                lot_id=f"LOT-{transaction_id}",
                source_transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                instrument_id=security_id,
                security_id=security_id,
                acquisition_date=transaction_date.date(),
                original_quantity=quantity,
                open_quantity=quantity,
                lot_cost_local=quantity * Decimal("100"),
                lot_cost_base=quantity * Decimal("100"),
            )
        )
    await async_db_session.commit()

    lot_repo = SqlAlchemyCostBasisLotRepository(async_db_session)
    records = await lot_repo.get_fifo_disposal_lot_checkpoint_records(
        portfolio_id=portfolio_id,
        security_id=security_id,
        required_quantity=Decimal("6"),
    )

    assert [record.transaction.transaction_id for record in records] == [
        "BUY_FIFO_01",
        "BUY_FIFO_02",
    ]
    await lot_repo.update_selected_open_lot_states(
        portfolio_id=portfolio_id,
        security_id=security_id,
        states_by_source_transaction_id={
            "BUY_FIFO_01": OpenLotState(
                quantity=Decimal(0),
                cost_local=Decimal(0),
                cost_base=Decimal(0),
            ),
            "BUY_FIFO_02": OpenLotState(
                quantity=Decimal("3"),
                cost_local=Decimal("300"),
                cost_base=Decimal("300"),
            ),
        },
    )
    await async_db_session.commit()

    lot_rows = list(
        (
            await async_db_session.execute(
                select(PositionLotState)
                .where(PositionLotState.portfolio_id == portfolio_id)
                .order_by(PositionLotState.source_transaction_id)
            )
        )
        .scalars()
        .all()
    )
    assert [lot.open_quantity for lot in lot_rows] == [
        Decimal(0),
        Decimal("3"),
        Decimal("7"),
    ]
    assert [lot.lot_cost_base for lot in lot_rows] == [
        Decimal(0),
        Decimal("300"),
        Decimal("700"),
    ]


async def test_cost_repository_upserts_buy_lot_state_idempotently(
    clean_db, async_db_session: AsyncSession
) -> None:
    async_db_session.add(
        Portfolio(
            portfolio_id="PORT_SLICE4_04",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="Medium",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CIF_SLICE4_04",
            status="ACTIVE",
        )
    )
    async_db_session.add(
        DBTransaction(
            transaction_id="TXN_SLICE4_04",
            portfolio_id="PORT_SLICE4_04",
            instrument_id="BOND_USD_04",
            security_id="BOND_USD_04",
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
            lot_id="LOT-TXN_SLICE4_04",
            source_transaction_id="TXN_SLICE4_04",
            portfolio_id="PORT_SLICE4_04",
            instrument_id="OLD_BOND_USD_04",
            security_id="OLD_BOND_USD_04",
            acquisition_date=date(2026, 2, 27),
            original_quantity=Decimal("50"),
            open_quantity=Decimal("25"),
            lot_cost_local=Decimal("4900"),
            lot_cost_base=Decimal("4900"),
            accrued_interest_paid_local=Decimal("0"),
            economic_event_id="OLD-EVT",
        )
    )
    await async_db_session.commit()

    lot_repo = SqlAlchemyCostBasisLotRepository(async_db_session)
    txn = EngineTransaction(
        transaction_id="TXN_SLICE4_04",
        portfolio_id="PORT_SLICE4_04",
        instrument_id="BOND_USD_04",
        security_id="BOND_USD_04",
        transaction_type="BUY",
        transaction_date=datetime(2026, 2, 28, 10, 0, 0),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("9800"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost_local=Decimal("9840.12"),
        net_cost=Decimal("9840.12"),
        accrued_interest=Decimal("125.55"),
        economic_event_id="EVT-2026-888",
        linked_transaction_group_id="LTG-2026-888",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.1",
        source_system="OMS_PRIMARY",
    )

    await lot_repo.upsert_buy_lot_state(txn)
    await async_db_session.commit()

    lot_stmt = select(PositionLotState).where(
        PositionLotState.source_transaction_id == "TXN_SLICE4_04"
    )
    lot = (await async_db_session.execute(lot_stmt)).scalar_one()
    assert lot.lot_id == "LOT-TXN_SLICE4_04"
    assert lot.source_transaction_id == "TXN_SLICE4_04"
    assert lot.instrument_id == "BOND_USD_04"
    assert lot.security_id == "BOND_USD_04"
    assert lot.acquisition_date == date(2026, 2, 28)
    assert lot.original_quantity == Decimal("100")
    assert lot.open_quantity == Decimal("100")
    assert lot.lot_cost_local == Decimal("9840.12")
    assert lot.lot_cost_base == Decimal("9840.12")
    assert lot.accrued_interest_paid_local == Decimal("125.55")
    assert lot.economic_event_id == "EVT-2026-888"
    assert lot.linked_transaction_group_id == "LTG-2026-888"
    assert lot.calculation_policy_version == "1.0.1"


async def test_cost_repository_replaces_transaction_cost_breakdown_idempotently(
    clean_db, async_db_session: AsyncSession
) -> None:
    async_db_session.add(
        Portfolio(
            portfolio_id="PORT_SLICE4_03",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="Medium",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CIF_SLICE4_03",
            status="ACTIVE",
        )
    )
    async_db_session.add(
        DBTransaction(
            transaction_id="TXN_SLICE4_03",
            portfolio_id="PORT_SLICE4_03",
            instrument_id="BOND_USD_03",
            security_id="BOND_USD_03",
            transaction_type="BUY",
            quantity=Decimal("100"),
            price=Decimal("98"),
            gross_transaction_amount=Decimal("9800"),
            trade_currency="USD",
            currency="USD",
            transaction_date=datetime(2026, 2, 28, 10, 0, 0),
        )
    )
    async_db_session.add(
        TransactionCost(
            transaction_id="TXN_SLICE4_03",
            fee_type="stale_fee",
            amount=Decimal("999"),
            currency="USD",
        )
    )
    await async_db_session.commit()

    repo = SqlAlchemyCostBasisTransactionRepository(async_db_session)
    txn = EngineTransaction(
        transaction_id="TXN_SLICE4_03",
        portfolio_id="PORT_SLICE4_03",
        instrument_id="BOND_USD_03",
        security_id="BOND_USD_03",
        transaction_type="BUY",
        transaction_date=datetime(2026, 2, 28, 10, 0, 0),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("9800"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        fees=Fees(
            brokerage=Decimal("12.34"),
            stamp_duty=Decimal("0"),
            exchange_fee=Decimal("1.25"),
            gst=Decimal("0"),
            other_fees=Decimal("0.01"),
        ),
    )

    await repo.replace_transaction_cost_breakdown(txn)
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(TransactionCost)
                .where(TransactionCost.transaction_id == "TXN_SLICE4_03")
                .order_by(TransactionCost.fee_type)
            )
        )
        .scalars()
        .all()
    )
    assert [(row.fee_type, row.amount, row.currency) for row in rows] == [
        ("brokerage", Decimal("12.34"), "USD"),
        ("exchange_fee", Decimal("1.25"), "USD"),
        ("other_fees", Decimal("0.01"), "USD"),
    ]
