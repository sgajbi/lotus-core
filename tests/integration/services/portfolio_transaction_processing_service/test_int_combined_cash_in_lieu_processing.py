from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import Cashflow, FxRate, PositionHistory, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    instrument_record,
    persist_and_process_booked_transaction,
    portfolio_record,
    process_booked_transaction,
    transaction_processing_test_context,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_cross_currency_cash_in_lieu_reconciles_fractional_product_and_cash_legs(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-CIL-01"
    target_security_id = "FO_EQ_COMBINED_CIL_01"
    cash_security_id = "CASH_EUR"
    linked_group_id = "GROUP-COMBINED-CIL-01"
    economic_event_id = "EVENT-COMBINED-CIL-01"
    cash_settlement_id = "ADJUSTMENT-COMBINED-CIL-CASH-01"
    transaction_time = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)

    acquisition = booked_transaction_event(
        transaction_id="BUY-COMBINED-CIL-TARGET-01",
        portfolio_id=portfolio_id,
        security_id=target_security_id,
        transaction_date=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10.5",
        price="100",
        gross_amount="1050",
        trade_currency="EUR",
    )
    cash_settlement = booked_transaction_event(
        transaction_id=cash_settlement_id,
        portfolio_id=portfolio_id,
        security_id=cash_security_id,
        transaction_date=transaction_time,
        transaction_type="ADJUSTMENT",
        quantity="0",
        price="0",
        gross_amount="60",
        trade_currency="EUR",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        movement_direction="INFLOW",
        originating_transaction_id="CASH-IN-LIEU-COMBINED-01",
        originating_transaction_type="CASH_IN_LIEU",
        adjustment_reason="CASH_IN_LIEU_SETTLEMENT",
        link_type="CASH_IN_LIEU_TO_CASH",
    )
    cash_in_lieu = booked_transaction_event(
        transaction_id="CASH-IN-LIEU-COMBINED-01",
        portfolio_id=portfolio_id,
        security_id=target_security_id,
        transaction_date=transaction_time,
        transaction_type="CASH_IN_LIEU",
        quantity="0.5",
        price="120",
        gross_amount="60",
        trade_currency="EUR",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        linked_cash_transaction_id=cash_settlement_id,
        external_cash_transaction_id=cash_settlement_id,
        cash_entry_mode="UPSTREAM_PROVIDED",
        allocated_cost_basis_local=Decimal("50"),
        allocated_cost_basis_base=Decimal("67.5"),
        realized_capital_pnl_local=Decimal("10"),
        realized_fx_pnl_local=Decimal("0"),
        realized_capital_pnl_base=Decimal("10"),
        realized_fx_pnl_base=Decimal("3.5"),
        has_synthetic_flow=True,
        synthetic_flow_effective_date=date(2026, 5, 10),
        synthetic_flow_amount_local=Decimal("-60"),
        synthetic_flow_currency="EUR",
        synthetic_flow_amount_base=Decimal("-81"),
        synthetic_flow_price_used=Decimal("120"),
        synthetic_flow_quantity_used=Decimal("0.5"),
        synthetic_flow_valuation_method="MVT_PRICE_X_QTY",
        synthetic_flow_classification="POSITION_CASH_IN_LIEU_OUT",
        synthetic_flow_price_source="UPSTREAM",
        synthetic_flow_source="UPSTREAM_PROVIDED",
    )

    async_db_session.add(portfolio_record(portfolio_id, base_currency="SGD"))
    async_db_session.add(
        instrument_record(
            target_security_id,
            name="Combined Cash In Lieu Target Equity",
            isin="SG0000000301",
            currency="EUR",
        )
    )
    async_db_session.add_all(
        [
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 5, 1),
                rate=Decimal("1.35"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 5, 11),
                rate=Decimal("1.40"),
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)

    results = []
    for offset, event in enumerate(
        (acquisition, cash_settlement, cash_in_lieu),
        start=9901,
    ):
        results.append(
            await persist_and_process_booked_transaction(
                session=async_db_session,
                context=context,
                event=event,
                event_id=f"transactions.persisted-0-{offset}",
                correlation_id=f"corr-{event.transaction_id.lower()}",
            )
        )
    duplicate = await process_booked_transaction(
        context=context,
        event=cash_in_lieu,
        event_id="transactions.persisted-0-9903",
        correlation_id="corr-cash-in-lieu-combined-01",
    )

    assert all(result.status is TransactionProcessingStatus.PROCESSED for result in results)
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        persisted_cash_in_lieu = await verification_session.scalar(
            select(DBTransaction).where(DBTransaction.transaction_id == cash_in_lieu.transaction_id)
        )
        persisted_cash_settlement = await verification_session.scalar(
            select(DBTransaction).where(
                DBTransaction.transaction_id == cash_settlement.transaction_id
            )
        )
        lot = await verification_session.scalar(
            select(PositionLotState).where(
                PositionLotState.source_transaction_id == acquisition.transaction_id
            )
        )
        positions = (
            (
                await verification_session.execute(
                    select(PositionHistory)
                    .where(PositionHistory.portfolio_id == portfolio_id)
                    .order_by(PositionHistory.id)
                )
            )
            .scalars()
            .all()
        )
        flows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(Cashflow.linked_transaction_group_id == linked_group_id)
                    .order_by(Cashflow.transaction_id)
                )
            )
            .scalars()
            .all()
        )

    assert persisted_cash_in_lieu is not None
    assert persisted_cash_in_lieu.transaction_fx_rate == Decimal("1.35")
    assert persisted_cash_in_lieu.allocated_cost_basis_local == Decimal("50")
    assert persisted_cash_in_lieu.allocated_cost_basis_base == Decimal("67.5")
    assert persisted_cash_in_lieu.net_cost_local == Decimal("-50")
    assert persisted_cash_in_lieu.net_cost == Decimal("-67.5")
    assert persisted_cash_in_lieu.realized_gain_loss_local == Decimal("10")
    assert persisted_cash_in_lieu.realized_gain_loss == Decimal("13.5")
    assert persisted_cash_in_lieu.realized_capital_pnl_local == Decimal("10")
    assert persisted_cash_in_lieu.realized_fx_pnl_local == Decimal("0")
    assert persisted_cash_in_lieu.realized_total_pnl_local == Decimal("10")
    assert persisted_cash_in_lieu.realized_capital_pnl_base == Decimal("10")
    assert persisted_cash_in_lieu.realized_fx_pnl_base == Decimal("3.5")
    assert persisted_cash_in_lieu.realized_total_pnl_base == Decimal("13.5")

    assert persisted_cash_settlement is not None
    assert persisted_cash_settlement.transaction_fx_rate == Decimal("1.35")
    assert persisted_cash_settlement.net_cost_local == Decimal("60")
    assert persisted_cash_settlement.net_cost == Decimal("81")

    assert lot is not None
    assert lot.open_quantity == Decimal("10")
    assert lot.lot_cost_local == Decimal("1000")
    assert lot.lot_cost_base == Decimal("1350")

    latest_position_by_security = {
        security_id: next(
            position for position in reversed(positions) if position.security_id == security_id
        )
        for security_id in {target_security_id, cash_security_id}
    }
    assert latest_position_by_security[target_security_id].quantity == Decimal("10")
    assert latest_position_by_security[target_security_id].cost_basis_local == Decimal("1000")
    assert latest_position_by_security[target_security_id].cost_basis == Decimal("1350")
    assert latest_position_by_security[cash_security_id].quantity == Decimal("60")
    assert latest_position_by_security[cash_security_id].cost_basis_local == Decimal("60")
    assert latest_position_by_security[cash_security_id].cost_basis == Decimal("81")

    flow_by_transaction = {flow.transaction_id: flow for flow in flows}
    product_flow = flow_by_transaction[cash_in_lieu.transaction_id]
    settlement_flow = flow_by_transaction[cash_settlement.transaction_id]
    assert product_flow.amount == Decimal("-60")
    assert product_flow.currency == "EUR"
    assert product_flow.is_position_flow is True
    assert settlement_flow.amount == Decimal("60")
    assert settlement_flow.currency == "EUR"
    assert settlement_flow.is_position_flow is False
    assert sum(flow.amount for flow in flows) == Decimal("0")
