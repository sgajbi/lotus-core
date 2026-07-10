from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import Cashflow, PositionHistory, PositionLotState
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


async def test_full_exchange_conserves_basis_and_balances_linked_mvt_flows(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-EXCHANGE-01"
    source_security_id = "FO_EQ_EXCHANGE_SOURCE_01"
    target_security_id = "FO_EQ_EXCHANGE_TARGET_01"
    economic_event_id = "EVT-EXCHANGE-01"
    linked_group_id = "GROUP-EXCHANGE-01"
    parent_reference = "PARENT-EXCHANGE-01"
    acquisition = booked_transaction_event(
        transaction_id="BUY-EXCHANGE-SOURCE-01",
        portfolio_id=portfolio_id,
        security_id=source_security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    source_out = booked_transaction_event(
        transaction_id="EXCHANGE-OUT-01",
        portfolio_id=portfolio_id,
        security_id=source_security_id,
        transaction_date=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="EXCHANGE_OUT",
        quantity="100",
        price="12",
        gross_amount="1000",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        parent_event_reference=parent_reference,
        source_instrument_id=source_security_id,
        target_instrument_id=target_security_id,
        target_transaction_reference="EXCHANGE-IN-01",
        has_synthetic_flow=True,
        synthetic_flow_effective_date=date(2026, 7, 5),
        synthetic_flow_amount_local=Decimal("-1200"),
        synthetic_flow_currency="USD",
        synthetic_flow_amount_base=Decimal("-1200"),
        synthetic_flow_price_used=Decimal("12"),
        synthetic_flow_quantity_used=Decimal("100"),
        synthetic_flow_valuation_method="MVT_PRICE_X_QTY",
        synthetic_flow_classification="POSITION_TRANSFER_OUT",
        synthetic_flow_price_source="UPSTREAM",
        synthetic_flow_source="UPSTREAM_PROVIDED",
    )
    target_in = booked_transaction_event(
        transaction_id="EXCHANGE-IN-01",
        portfolio_id=portfolio_id,
        security_id=target_security_id,
        transaction_date=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="EXCHANGE_IN",
        quantity="50",
        price="24",
        gross_amount="1000",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        parent_event_reference=parent_reference,
        source_instrument_id=source_security_id,
        target_instrument_id=target_security_id,
        source_transaction_reference="EXCHANGE-OUT-01",
        dependency_reference_ids=["EXCHANGE-OUT-01"],
        has_synthetic_flow=True,
        synthetic_flow_effective_date=date(2026, 7, 5),
        synthetic_flow_amount_local=Decimal("1200"),
        synthetic_flow_currency="USD",
        synthetic_flow_amount_base=Decimal("1200"),
        synthetic_flow_price_used=Decimal("24"),
        synthetic_flow_quantity_used=Decimal("50"),
        synthetic_flow_valuation_method="MVT_PRICE_X_QTY",
        synthetic_flow_classification="POSITION_TRANSFER_IN",
        synthetic_flow_price_source="UPSTREAM",
        synthetic_flow_source="UPSTREAM_PROVIDED",
    )
    async_db_session.add(portfolio_record(portfolio_id, cost_basis_method="AVCO"))
    async_db_session.add_all(
        [
            instrument_record(
                source_security_id,
                name="Exchange Source Equity",
                isin="SG0000000101",
                currency="USD",
            ),
            instrument_record(
                target_security_id,
                name="Exchange Target Equity",
                isin="SG0000000102",
                currency="USD",
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)

    results = []
    for offset, event in enumerate((acquisition, source_out, target_in), start=9601):
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
        event=target_in,
        event_id="transactions.persisted-0-9603",
        correlation_id="corr-exchange-in-01",
    )

    assert all(result.status is TransactionProcessingStatus.PROCESSED for result in results)
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        transactions = (
            (
                await verification_session.execute(
                    select(DBTransaction).where(
                        DBTransaction.transaction_id.in_(
                            [source_out.transaction_id, target_in.transaction_id]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.portfolio_id == portfolio_id)
                    .order_by(PositionLotState.source_transaction_id)
                )
            )
            .scalars()
            .all()
        )
        positions = (
            (
                await verification_session.execute(
                    select(PositionHistory)
                    .where(PositionHistory.portfolio_id == portfolio_id)
                    .order_by(PositionHistory.position_date, PositionHistory.id)
                )
            )
            .scalars()
            .all()
        )
        transfer_flows = (
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

    transaction_by_id = {transaction.transaction_id: transaction for transaction in transactions}
    assert transaction_by_id[source_out.transaction_id].net_cost == Decimal("-1000")
    assert transaction_by_id[source_out.transaction_id].realized_gain_loss is None
    assert transaction_by_id[target_in.transaction_id].net_cost == Decimal("1000")
    assert transaction_by_id[target_in.transaction_id].realized_gain_loss is None
    assert all(
        transaction.economic_event_id == economic_event_id
        and transaction.linked_transaction_group_id == linked_group_id
        and transaction.parent_event_reference == parent_reference
        for transaction in transactions
    )
    assert [(lot.source_transaction_id, lot.open_quantity, lot.lot_cost_base) for lot in lots] == [
        (acquisition.transaction_id, Decimal("0"), Decimal("0")),
        (target_in.transaction_id, Decimal("50"), Decimal("1000")),
    ]
    assert [
        (position.security_id, position.quantity, position.cost_basis) for position in positions
    ] == [
        (source_security_id, Decimal("100"), Decimal("1000")),
        (source_security_id, Decimal("0"), Decimal("0")),
        (target_security_id, Decimal("50"), Decimal("1000")),
    ]
    assert [
        (
            flow.transaction_id,
            flow.amount,
            flow.calculation_type,
            flow.timing,
            flow.is_position_flow,
            flow.is_portfolio_flow,
        )
        for flow in transfer_flows
    ] == [
        (target_in.transaction_id, Decimal("1200"), "MVT", "BOD", True, False),
        (source_out.transaction_id, Decimal("-1200"), "MVT", "EOD", True, False),
    ]
    assert sum(flow.amount for flow in transfer_flows) == Decimal("0")
    assert sum(lot.lot_cost_base for lot in lots) == Decimal("1000")
