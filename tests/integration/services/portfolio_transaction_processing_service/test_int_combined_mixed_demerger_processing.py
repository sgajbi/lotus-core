from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    PositionHistory,
    PositionLotState,
    ProcessedEvent,
)
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.idempotency import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
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


async def test_mixed_demerger_conserves_basis_and_balances_product_flows(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-MIXED-DEMERGER-01"
    source_security_id = "FO_EQ_DEMERGER_SOURCE_01"
    target_security_id = "FO_EQ_DEMERGER_CHILD_01"
    cash_security_id = "CASH_USD"
    economic_event_id = "EVT-MIXED-DEMERGER-01"
    linked_group_id = "GROUP-MIXED-DEMERGER-01"
    parent_reference = "PARENT-MIXED-DEMERGER-01"
    cash_settlement_id = "CASH-SETTLEMENT-MIXED-DEMERGER-01"
    transaction_time = datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc)

    acquisition = booked_transaction_event(
        transaction_id="BUY-MIXED-DEMERGER-SOURCE-01",
        portfolio_id=portfolio_id,
        security_id=source_security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    source_out = booked_transaction_event(
        transaction_id="DEMERGER-OUT-MIXED-01",
        portfolio_id=portfolio_id,
        security_id=source_security_id,
        transaction_date=transaction_time,
        transaction_type="DEMERGER_OUT",
        quantity="0",
        price="0",
        gross_amount="300",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        parent_event_reference=parent_reference,
        source_instrument_id=source_security_id,
        target_instrument_id=target_security_id,
        target_transaction_reference="DEMERGER-IN-MIXED-01",
        has_synthetic_flow=True,
        synthetic_flow_effective_date=date(2026, 7, 5),
        synthetic_flow_amount_local=Decimal("-1450"),
        synthetic_flow_currency="USD",
        synthetic_flow_amount_base=Decimal("-1450"),
        synthetic_flow_price_used=Decimal("14.50"),
        synthetic_flow_quantity_used=Decimal("100"),
        synthetic_flow_valuation_method="MVT_PRICE_X_QTY",
        synthetic_flow_classification="POSITION_TRANSFER_OUT",
        synthetic_flow_price_source="UPSTREAM",
        synthetic_flow_source="UPSTREAM_PROVIDED",
    )
    target_in = booked_transaction_event(
        transaction_id="DEMERGER-IN-MIXED-01",
        portfolio_id=portfolio_id,
        security_id=target_security_id,
        transaction_date=transaction_time,
        transaction_type="DEMERGER_IN",
        quantity="25",
        price="48",
        gross_amount="250",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        parent_event_reference=parent_reference,
        source_instrument_id=source_security_id,
        target_instrument_id=target_security_id,
        source_transaction_reference=source_out.transaction_id,
        dependency_reference_ids=[source_out.transaction_id],
        has_synthetic_flow=True,
        synthetic_flow_effective_date=date(2026, 7, 5),
        synthetic_flow_amount_local=Decimal("1200"),
        synthetic_flow_currency="USD",
        synthetic_flow_amount_base=Decimal("1200"),
        synthetic_flow_price_used=Decimal("48"),
        synthetic_flow_quantity_used=Decimal("25"),
        synthetic_flow_valuation_method="MVT_PRICE_X_QTY",
        synthetic_flow_classification="POSITION_TRANSFER_IN",
        synthetic_flow_price_source="UPSTREAM",
        synthetic_flow_source="UPSTREAM_PROVIDED",
    )
    cash_settlement = booked_transaction_event(
        transaction_id=cash_settlement_id,
        portfolio_id=portfolio_id,
        security_id=cash_security_id,
        transaction_date=transaction_time,
        transaction_type="ADJUSTMENT",
        quantity="0",
        price="0",
        gross_amount="250",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        parent_event_reference=parent_reference,
        movement_direction="INFLOW",
        originating_transaction_id="CASH-CONSIDERATION-MIXED-01",
        originating_transaction_type="CASH_CONSIDERATION",
        adjustment_reason="CASH_CONSIDERATION_SETTLEMENT",
        link_type="CASH_CONSIDERATION_TO_CASH",
    )
    cash_consideration = booked_transaction_event(
        transaction_id="CASH-CONSIDERATION-MIXED-01",
        portfolio_id=portfolio_id,
        security_id=source_security_id,
        transaction_date=transaction_time,
        transaction_type="CASH_CONSIDERATION",
        quantity="0",
        price="0",
        gross_amount="250",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        parent_event_reference=parent_reference,
        linked_cash_transaction_id=cash_settlement_id,
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=cash_settlement_id,
        allocated_cost_basis_local=Decimal("50"),
        allocated_cost_basis_base=Decimal("50"),
        dependency_reference_ids=[
            source_out.transaction_id,
            target_in.transaction_id,
        ],
    )

    async_db_session.add(portfolio_record(portfolio_id, cost_basis_method="AVCO"))
    async_db_session.add_all(
        [
            instrument_record(
                source_security_id,
                name="Mixed Demerger Source Equity",
                isin="SG0000000201",
                currency="USD",
            ),
            instrument_record(
                target_security_id,
                name="Mixed Demerger Child Equity",
                isin="SG0000000202",
                currency="USD",
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)

    results = []
    events = (acquisition, source_out, target_in, cash_settlement, cash_consideration)
    for offset, event in enumerate(events, start=9701):
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
        event=cash_consideration,
        event_id="transactions.persisted-0-9705",
        correlation_id="corr-cash-consideration-mixed-01",
    )

    assert all(result.status is TransactionProcessingStatus.PROCESSED for result in results)
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        transactions = (
            (
                await verification_session.execute(
                    select(DBTransaction).where(
                        DBTransaction.transaction_id.in_(
                            [
                                source_out.transaction_id,
                                target_in.transaction_id,
                                cash_consideration.transaction_id,
                            ]
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
                    .order_by(PositionHistory.security_id, PositionHistory.position_date)
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
        reconciliation_runs = (
            (
                await verification_session.execute(
                    select(FinancialReconciliationRun)
                    .where(
                        FinancialReconciliationRun.portfolio_id == portfolio_id,
                        FinancialReconciliationRun.reconciliation_type
                        == "corporate_action_bundle_a",
                    )
                    .order_by(FinancialReconciliationRun.id)
                )
            )
            .scalars()
            .all()
        )
        reconciliation_findings = (
            (
                await verification_session.execute(
                    select(FinancialReconciliationFinding).where(
                        FinancialReconciliationFinding.portfolio_id == portfolio_id
                    )
                )
            )
            .scalars()
            .all()
        )

    transaction_by_id = {transaction.transaction_id: transaction for transaction in transactions}
    source_transaction = transaction_by_id[source_out.transaction_id]
    target_transaction = transaction_by_id[target_in.transaction_id]
    cash_transaction = transaction_by_id[cash_consideration.transaction_id]
    assert source_transaction.net_cost == Decimal("-300")
    assert target_transaction.net_cost == Decimal("250")
    assert cash_transaction.allocated_cost_basis_local == Decimal("50")
    assert cash_transaction.allocated_cost_basis_base == Decimal("50")
    assert cash_transaction.net_cost_local == Decimal("-50")
    assert cash_transaction.net_cost == Decimal("-50")
    assert cash_transaction.realized_gain_loss_local == Decimal("200")
    assert cash_transaction.realized_gain_loss == Decimal("200")
    assert cash_transaction.realized_capital_pnl_local == Decimal("200")
    assert cash_transaction.realized_fx_pnl_local == Decimal("0")
    assert cash_transaction.realized_total_pnl_local == Decimal("200")
    assert cash_transaction.realized_capital_pnl_base == Decimal("200")
    assert cash_transaction.realized_fx_pnl_base == Decimal("0")
    assert cash_transaction.realized_total_pnl_base == Decimal("200")

    lot_by_source = {lot.source_transaction_id: lot for lot in lots}
    assert lot_by_source[acquisition.transaction_id].open_quantity == Decimal("100")
    assert lot_by_source[acquisition.transaction_id].lot_cost_base == Decimal("700")
    assert lot_by_source[target_in.transaction_id].open_quantity == Decimal("25")
    assert lot_by_source[target_in.transaction_id].lot_cost_base == Decimal("250")
    assert sum(lot.lot_cost_base for lot in lots) + cash_transaction.allocated_cost_basis_base == (
        Decimal("1000")
    )

    latest_position_by_security = {
        security_id: next(
            position for position in reversed(positions) if position.security_id == security_id
        )
        for security_id in {source_security_id, target_security_id, cash_security_id}
    }
    assert latest_position_by_security[source_security_id].quantity == Decimal("100")
    assert latest_position_by_security[source_security_id].cost_basis == Decimal("700")
    assert latest_position_by_security[target_security_id].quantity == Decimal("25")
    assert latest_position_by_security[target_security_id].cost_basis == Decimal("250")
    assert latest_position_by_security[cash_security_id].quantity == Decimal("250")
    assert latest_position_by_security[cash_security_id].cost_basis == Decimal("250")

    flow_by_transaction = {flow.transaction_id: flow for flow in flows}
    assert flow_by_transaction[source_out.transaction_id].amount == Decimal("-1450")
    assert flow_by_transaction[target_in.transaction_id].amount == Decimal("1200")
    assert flow_by_transaction[cash_consideration.transaction_id].amount == Decimal("250")
    assert (
        flow_by_transaction[cash_consideration.transaction_id].classification
        == "CORPORATE_ACTION_PROCEEDS"
    )
    product_flows = [flow for flow in flows if flow.is_position_flow]
    assert sum(flow.amount for flow in product_flows) == Decimal("0")
    settlement_flow = flow_by_transaction[cash_settlement_id]
    assert settlement_flow.amount == Decimal("250")
    assert settlement_flow.is_position_flow is False
    assert settlement_flow.is_portfolio_flow is False

    balanced_runs = [
        run
        for run in reconciliation_runs
        if run.summary and run.summary.get("reconciliation_status") == "balanced"
    ]
    assert balanced_runs
    balanced_summary = balanced_runs[-1].summary
    assert balanced_summary["source_basis_out_local"] == "300.0000000000"
    assert balanced_summary["target_basis_in_local"] == "250.0000000000"
    assert balanced_summary["cash_basis_local"] == "50.0000000000"
    assert balanced_summary["net_basis_delta_local"] == "0E-10"
    assert balanced_summary["passed"] is True
    assert not any(
        finding.run_id == balanced_runs[-1].run_id for finding in reconciliation_findings
    )


async def test_cash_consideration_missing_allocated_basis_rolls_back_processing_outputs(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-MIXED-DEMERGER-ROLLBACK-01"
    security_id = "FO_EQ_DEMERGER_ROLLBACK_SOURCE_01"
    event_id = "transactions.persisted-0-9799"
    invalid_event = booked_transaction_event(
        transaction_id="CASH-CONSIDERATION-MISSING-BASIS-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="CASH_CONSIDERATION",
        quantity="0",
        price="0",
        gross_amount="250",
        economic_event_id="EVT-MIXED-DEMERGER-ROLLBACK-01",
        linked_transaction_group_id="GROUP-MIXED-DEMERGER-ROLLBACK-01",
        parent_event_reference="PARENT-MIXED-DEMERGER-ROLLBACK-01",
        linked_cash_transaction_id="CASH-SETTLEMENT-MISSING-BASIS-01",
    )
    async_db_session.add(portfolio_record(portfolio_id))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Mixed Demerger Rollback Source Equity",
            isin="SG0000000299",
            currency="USD",
        )
    )
    async_db_session.add(canonical_transaction_record(invalid_event))
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    with pytest.raises(ValueError, match="allocated_cost_basis_local is required"):
        await process_booked_transaction(
            context=context,
            event=invalid_event,
            event_id=event_id,
            correlation_id="corr-cash-consideration-missing-basis",
        )

    async with context.session_factory() as verification_session:
        transaction = await verification_session.scalar(
            select(DBTransaction).where(
                DBTransaction.transaction_id == invalid_event.transaction_id
            )
        )
        cashflow = await verification_session.scalar(
            select(Cashflow).where(Cashflow.transaction_id == invalid_event.transaction_id)
        )
        position = await verification_session.scalar(
            select(PositionHistory).where(
                PositionHistory.transaction_id == invalid_event.transaction_id
            )
        )
        processed_event = await verification_session.scalar(
            select(ProcessedEvent).where(
                ProcessedEvent.event_id == event_id,
                ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
            )
        )

    assert transaction is not None
    assert transaction.net_cost is None
    assert transaction.realized_gain_loss is None
    assert cashflow is None
    assert position is None
    assert processed_event is None
