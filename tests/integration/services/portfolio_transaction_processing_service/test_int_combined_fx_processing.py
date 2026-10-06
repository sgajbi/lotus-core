from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from portfolio_common.database_models import (
    AverageCostPoolState,
    CashAccountMaster,
    Cashflow,
    FxRate,
    LotBasisTransferReceiptRecord,
    LotDisposalReceiptRecord,
    OutboxEvent,
    PipelineStageState,
    PositionHistory,
    PositionLotState,
    PositionState,
    ProcessedEvent,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.calculation_lineage import calculation_lineage_binds_output
from portfolio_common.domain.transaction import build_transaction_payload_identity
from portfolio_common.event_mapping import transaction_event_v1_payload
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)
from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingError,
    TransactionProcessingIntent,
    TransactionProcessingRejected,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.settlement.generated_cash_leg import (  # noqa: E501
    _generated_cash_lineage_output,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.transaction_repository import (  # noqa: E501
    _to_persisted_booked_transaction,
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


async def _account_application_snapshot(factory):
    models = (
        DBTransaction,
        TransactionCost,
        PositionLotState,
        AverageCostPoolState,
        Cashflow,
        PositionHistory,
        PositionState,
        ProcessedEvent,
        PipelineStageState,
        LotDisposalReceiptRecord,
        LotBasisTransferReceiptRecord,
        OutboxEvent,
    )
    async with factory() as verification:
        snapshot = {}
        for model in models:
            table = model.__table__
            rows = (
                (
                    await verification.execute(
                        select(*table.columns).order_by(*table.primary_key.columns)
                    )
                )
                .mappings()
                .all()
            )
            snapshot[table.name] = [dict(row) for row in rows]
        return snapshot


@pytest.mark.parametrize("mapping", ["owned", "foreign_owner", "currency_mismatch"])
async def test_generated_cash_account_mapping_has_atomic_application_outcome(
    clean_db, async_db_session: AsyncSession, mapping
):
    """Qualify actual generated settlement mapping, not raw FX-account admission."""
    portfolio_id, other_portfolio = "PORT-ACCOUNT-BATCH", "PORT-ACCOUNT-FOREIGN"
    security_id, cash_id = "EQ-ACCOUNT-BATCH", "CASH-ACCOUNT-BATCH"
    async_db_session.add_all([portfolio_record(portfolio_id), portfolio_record(other_portfolio)])
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id, name="Account batch equity", isin="SGACCOUNT001", currency="USD"
            ),
            instrument_record(
                cash_id,
                name="Account batch cash",
                isin="CAACCOUNT001",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=other_portfolio if mapping == "foreign_owner" else portfolio_id,
                security_id=cash_id,
                display_name="Settlement account authority",
                account_currency="EUR" if mapping == "currency_mismatch" else "USD",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
        ]
    )
    await async_db_session.flush()
    event = booked_transaction_event(
        transaction_id="DIV-ACCOUNT-BATCH",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="100",
        trade_currency="USD",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=cash_id,
    )
    assert (
        await TransactionDBRepository(async_db_session).create_or_update_transaction(event)
    ).inserted
    async_db_session.add(
        OutboxEvent(
            aggregate_type="RawTransaction",
            aggregate_id=portfolio_id,
            event_type="RawTransactionPersisted",
            topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            payload=transaction_event_v1_payload(event),
        )
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    before = await _account_application_snapshot(context.session_factory)
    kwargs = dict(
        context=context, event=event, event_id="ACCOUNT-BATCH", correlation_id="ACCOUNT-BATCH"
    )
    if mapping == "owned":
        result = await process_booked_transaction(**kwargs)
        assert result.status is TransactionProcessingStatus.PROCESSED
        after = await _account_application_snapshot(context.session_factory)
        child = [
            row
            for row in after["transactions"]
            if row["transaction_id"] == event.transaction_id + "-CASHLEG"
        ]
        assert len(child) == 1
        assert child[0]["portfolio_id"] == portfolio_id and child[0]["security_id"] == cash_id
        assert child[0]["currency"] == "USD"
        assert child[0]["gross_transaction_amount"] == Decimal("100")
        assert child[0]["quantity"] == Decimal(0)
        assert child[0]["net_cost"] == child[0]["net_cost_local"] == Decimal("100")
        assert child[0]["originating_transaction_id"] == event.transaction_id
        assert child[0]["payload_fingerprint"]
        async with context.session_factory() as verification:
            child_row = (
                await verification.execute(
                    select(DBTransaction).where(
                        DBTransaction.transaction_id == event.transaction_id + "-CASHLEG"
                    )
                )
            ).scalar_one()
            final = _to_persisted_booked_transaction(child_row, tenant_id=event.tenant_id)
            assert calculation_lineage_binds_output(
                final.calculation_lineage, output_payload=_generated_cash_lineage_output(final)
            )
            print("ACCOUNT_BATCH_BOUND_RECEIPT", final.calculation_lineage.lineage_payload())
        assert (
            await process_booked_transaction(**kwargs)
        ).status is TransactionProcessingStatus.DUPLICATE
        assert await _account_application_snapshot(context.session_factory) == after
    else:
        error = (
            TransactionProcessingError
            if mapping == "foreign_owner"
            else TransactionProcessingRejected
        )
        with pytest.raises(error) as raised:
            await process_booked_transaction(**kwargs)
        assert raised.value.reason_code == (
            "cost_dependency_unavailable"
            if mapping == "foreign_owner"
            else "settlement_cash_account_currency_mismatch"
        )
        assert raised.value.retryable is (mapping == "foreign_owner")
        assert await _account_application_snapshot(context.session_factory) == before
        after = before
    raw_after = [row for row in after["outbox_events"] if row["aggregate_type"] == "RawTransaction"]
    assert raw_after == before["outbox_events"]
    async with context.session_factory() as observer:
        active = (
            (
                await observer.execute(
                    text(
                        "SELECT pid,state,query FROM pg_stat_activity "
                        "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                        "AND backend_type='client backend' AND state<>'idle'"
                    )
                )
            )
            .mappings()
            .all()
        )
        assert not active
        print("ACCOUNT_BATCH_ATOMIC_OUTCOME", mapping, "generated-settlement-only", list(active))


async def test_combined_cross_currency_buy_uses_effective_fx_rate(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-FX-01"
    security_id = "FO_EQ_COMBINED_FX_01"
    transaction_date = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    event = booked_transaction_event(
        transaction_id="BUY-COMBINED-FX-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=transaction_date,
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_amount="1000",
        trade_fee="10",
        trade_currency="EUR",
    )
    async_db_session.add(portfolio_record(portfolio_id, base_currency="SGD"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing Cross Currency Equity",
            isin="SG0000000003",
            currency="EUR",
        )
    )
    async_db_session.add_all(
        [
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 5, 1),
                rate=Decimal("1.40"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 5, 9),
                rate=Decimal("1.45"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 5, 11),
                rate=Decimal("1.50"),
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-9301",
        correlation_id="corr-combined-fx-buy-01",
    )

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert result.cashflow_record_count == 1
    assert result.position_record_count == 1

    async with context.session_factory() as verification_session:
        persisted_transaction = (
            await verification_session.execute(
                select(DBTransaction).where(DBTransaction.transaction_id == event.transaction_id)
            )
        ).scalar_one()
        lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == event.transaction_id
                )
            )
        ).scalar_one()
        transaction_cost = (
            await verification_session.execute(
                select(TransactionCost).where(
                    TransactionCost.transaction_id == event.transaction_id
                )
            )
        ).scalar_one()
        cashflow = (
            await verification_session.execute(
                select(Cashflow).where(Cashflow.transaction_id == event.transaction_id)
            )
        ).scalar_one()
        position = (
            await verification_session.execute(
                select(PositionHistory).where(
                    PositionHistory.transaction_id == event.transaction_id
                )
            )
        ).scalar_one()

    assert persisted_transaction.transaction_fx_rate == Decimal("1.45")
    assert persisted_transaction.net_cost_local == Decimal("1010")
    assert persisted_transaction.net_cost == Decimal("1464.50")
    assert lot.lot_cost_local == Decimal("1010")
    assert lot.lot_cost_base == Decimal("1464.50")
    assert (transaction_cost.fee_type, transaction_cost.amount, transaction_cost.currency) == (
        "brokerage",
        Decimal("10"),
        "EUR",
    )
    assert (cashflow.amount, cashflow.currency) == (Decimal("-1010"), "EUR")
    assert (position.cost_basis, position.cost_basis_local) == (
        Decimal("1464.50"),
        Decimal("1010"),
    )


async def test_source_booked_fx_governs_product_and_generated_cash_basis(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-SOURCE-BOOKED-FX-01"
    security_id = "FO_EQ_SOURCE_BOOKED_FX_01"
    cash_id = "CASH-XTS-SOURCE-BOOKED-01"
    transaction_id = "BUY-SOURCE-BOOKED-FX-01"
    transaction_date = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=transaction_date,
        settlement_date=transaction_date,
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_amount="1000",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=cash_id,
    )
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="Source-booked FX equity",
                isin="SG0000001155",
                currency="XTS",
            ),
            instrument_record(
                cash_id,
                name="Source-booked FX cash",
                isin="CASHXTS115501",
                currency="XTS",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=portfolio_id,
                security_id=cash_id,
                display_name="Source-booked FX cash",
                account_currency="XTS",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
            FxRate(
                from_currency="XTS",
                to_currency="USD",
                rate_date=date(2026, 4, 9),
                rate=Decimal("2.5"),
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-source-booked-fx",
        correlation_id="corr-source-booked-fx",
    )

    cash_leg_id = f"{transaction_id}-CASHLEG"
    async with context.session_factory() as verification_session:
        persisted = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id.in_([transaction_id, cash_leg_id])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        positions = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(PositionHistory).where(
                            PositionHistory.transaction_id.in_([transaction_id, cash_leg_id])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert persisted[transaction_id].transaction_fx_rate == Decimal("2.0")
    assert persisted[cash_leg_id].transaction_fx_rate == Decimal("2.0")
    assert positions[transaction_id].cost_basis == Decimal("2000")
    assert positions[cash_leg_id].cost_basis == Decimal("-2000")

    async with context.session_factory() as correction_session:
        reference_rate = (
            await correction_session.execute(
                select(FxRate).where(
                    FxRate.from_currency == "XTS",
                    FxRate.to_currency == "USD",
                    FxRate.rate_date == date(2026, 4, 9),
                )
            )
        ).scalar_one()
        reference_rate.rate = Decimal("3.0")
        await correction_session.commit()

    replay = await process_booked_transaction(
        context=context,
        event=event,
        event_id="transactions.persisted-0-source-booked-fx-replay",
        correlation_id="corr-source-booked-fx-replay",
    )

    assert replay.status is TransactionProcessingStatus.DUPLICATE
    async with context.session_factory() as replay_session:
        replay_positions = {
            row.transaction_id: row
            for row in (
                (
                    await replay_session.execute(
                        select(PositionHistory).where(
                            PositionHistory.transaction_id.in_([transaction_id, cash_leg_id])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
    assert replay_positions[transaction_id].cost_basis == Decimal("2000")
    assert replay_positions[cash_leg_id].cost_basis == Decimal("-2000")

    backdated_event = booked_transaction_event(
        transaction_id="DIVIDEND-SOURCE-BOOKED-FX-BACKDATED-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="10",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=cash_id,
    )
    backdated_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=backdated_event,
        event_id="transactions.persisted-0-source-booked-fx-backdated",
        correlation_id="corr-source-booked-fx-backdated",
    )

    assert backdated_result.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as rebuild_session:
        original_lot = (
            await rebuild_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == transaction_id
                )
            )
        ).scalar_one()
    assert original_lot.lot_cost_base == Decimal("2000")

    sell_event = booked_transaction_event(
        transaction_id="SELL-SOURCE-BOOKED-FX-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="10",
        price="110",
        gross_amount="1100",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("2.5"),
    )
    sell_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=sell_event,
        event_id="transactions.persisted-0-source-booked-fx-sell",
        correlation_id="corr-source-booked-fx-sell",
    )

    assert sell_result.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as disposal_session:
        persisted_sell = (
            await disposal_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == sell_event.transaction_id
                )
            )
        ).scalar_one()
    assert persisted_sell.realized_gain_loss == Decimal("750")


async def test_generated_cash_without_source_fx_uses_settlement_date_rate(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-DERIVED-SETTLEMENT-FX-01"
    security_id = "FO_EQ_DERIVED_SETTLEMENT_FX_01"
    cash_id = "CASH-XTS-DERIVED-SETTLEMENT-01"
    backdated_cash_id = "CASH-XTS-DERIVED-SETTLEMENT-02"
    transaction_id = "BUY-DERIVED-SETTLEMENT-FX-01"
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="Derived settlement FX equity",
                isin="SG0000001158",
                currency="XTS",
            ),
            instrument_record(
                cash_id,
                name="Derived settlement FX cash",
                isin="CASHXTS115801",
                currency="XTS",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=portfolio_id,
                security_id=cash_id,
                display_name="Mapped XTS settlement cash",
                account_currency="XTS",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
            instrument_record(
                backdated_cash_id,
                name="Backdated derived settlement FX cash",
                isin="CASHXTS115802",
                currency="XTS",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=backdated_cash_id,
                portfolio_id=portfolio_id,
                security_id=backdated_cash_id,
                display_name="Backdated mapped XTS settlement cash",
                account_currency="XTS",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
            FxRate(
                from_currency="XTS",
                to_currency="USD",
                rate_date=date(2026, 4, 9),
                rate=Decimal("2.0"),
            ),
            FxRate(
                from_currency="XTS",
                to_currency="USD",
                rate_date=date(2026, 4, 10),
                rate=Decimal("2.5"),
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_amount="1000",
        trade_currency="XTS",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=None,
    )

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-derived-settlement-fx",
        correlation_id="corr-derived-settlement-fx",
    )

    cash_leg_id = f"{transaction_id}-CASHLEG"
    async with context.session_factory() as verification_session:
        persisted = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id.in_([transaction_id, cash_leg_id])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        positions = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(PositionHistory).where(
                            PositionHistory.transaction_id.in_([transaction_id, cash_leg_id])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert persisted[transaction_id].transaction_fx_rate == Decimal("2.0")
    assert persisted[transaction_id].settlement_cash_instrument_id is None
    assert persisted[cash_leg_id].transaction_fx_rate == Decimal("2.5")
    assert persisted[cash_leg_id].security_id == cash_id
    assert positions[transaction_id].cost_basis == Decimal("2000")
    assert positions[cash_leg_id].cost_basis == Decimal("-2500")

    backdated_event = booked_transaction_event(
        transaction_id="DIVIDEND-DERIVED-SETTLEMENT-FX-BACKDATED-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="10",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=backdated_cash_id,
        settlement_cash_instrument_id=backdated_cash_id,
    )
    backdated_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=backdated_event,
        event_id="transactions.persisted-0-derived-settlement-fx-backdated",
        correlation_id="corr-derived-settlement-fx-backdated",
    )

    assert backdated_result.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as rebuild_session:
        rebuilt_cash = (
            await rebuild_session.execute(
                select(DBTransaction).where(DBTransaction.transaction_id == cash_leg_id)
            )
        ).scalar_one()
        rebuilt_cash_position = (
            await rebuild_session.execute(
                select(PositionHistory)
                .where(PositionHistory.transaction_id == cash_leg_id)
                .order_by(PositionHistory.id.desc())
                .limit(1)
            )
        ).scalar_one()
    assert rebuilt_cash.transaction_fx_rate == Decimal("2.5")
    assert rebuilt_cash.security_id == cash_id
    assert rebuilt_cash_position.cost_basis == Decimal("-2500")


async def test_omitted_cash_mode_and_instrument_replay_from_durable_state(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-MAPPED-CASH-REPLAY-01"
    security_id = "FO_EQ_MAPPED_CASH_REPLAY_01"
    cash_id = "CASH-USD-MAPPED-REPLAY-01"
    backdated_cash_id = "CASH-USD-MAPPED-REPLAY-02"
    transaction_id = "DIVIDEND-MAPPED-CASH-REPLAY-01"
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="Mapped cash replay equity",
                isin="SG000000MCR1",
                currency="USD",
            ),
            instrument_record(
                cash_id,
                name="Mapped USD cash",
                isin="CASHUSDMCR01",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=portfolio_id,
                security_id=cash_id,
                display_name="Mapped USD cash",
                account_currency="USD",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
            instrument_record(
                backdated_cash_id,
                name="Backdated mapped USD cash",
                isin="CASHUSDMCR02",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=backdated_cash_id,
                portfolio_id=portfolio_id,
                security_id=backdated_cash_id,
                display_name="Backdated mapped USD cash",
                account_currency="USD",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
        ]
    )
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="100",
        trade_currency="USD",
        cash_entry_mode=None,
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=None,
    )
    expected_raw_fingerprint = build_transaction_payload_identity(
        event.model_dump(mode="python"), tenant_id=event.tenant_id
    ).payload_fingerprint
    context = transaction_processing_test_context(async_db_session)

    initial = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-mapped-cash-replay",
        correlation_id="corr-mapped-cash-replay",
    )
    duplicate = await process_booked_transaction(
        context=context,
        event=event,
        event_id="transactions.persisted-0-mapped-cash-replay-duplicate",
        correlation_id="corr-mapped-cash-replay",
    )
    backdated_transaction_id = "DIVIDEND-MAPPED-CASH-REPLAY-BACKDATED-01"
    backdated = booked_transaction_event(
        transaction_id=backdated_transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="10",
        trade_currency="USD",
        cash_entry_mode=None,
        settlement_cash_account_id=backdated_cash_id,
        settlement_cash_instrument_id=None,
    )
    rebuilt = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=backdated,
        event_id="transactions.persisted-0-mapped-cash-replay-backdated",
        correlation_id="corr-mapped-cash-replay",
    )

    assert initial.status is TransactionProcessingStatus.PROCESSED
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE
    assert rebuilt.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as verification_session:
        rows = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id.in_(
                                [
                                    transaction_id,
                                    f"{transaction_id}-CASHLEG",
                                    f"{backdated_transaction_id}-CASHLEG",
                                ]
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
    assert rows[transaction_id].cash_entry_mode == "AUTO_GENERATE"
    assert rows[transaction_id].settlement_cash_instrument_id is None
    assert rows[transaction_id].payload_fingerprint == expected_raw_fingerprint
    assert rows[f"{transaction_id}-CASHLEG"].security_id == cash_id
    assert rows[f"{transaction_id}-CASHLEG"].net_cost_local == Decimal("100")
    assert rows[f"{backdated_transaction_id}-CASHLEG"].security_id == backdated_cash_id
    assert rows[f"{backdated_transaction_id}-CASHLEG"].net_cost_local == Decimal("10")


async def test_source_booked_fx_only_correction_is_material_and_idempotent(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-SOURCE-FX-CORRECTION-01"
    security_id = "FO_EQ_SOURCE_FX_CORRECTION_01"
    transaction_id = "BUY-SOURCE-FX-CORRECTION-01"
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Source FX correction equity",
            isin="SG000000FXC1",
            currency="XTS",
        )
    )
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_amount="1000",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
    )
    context = transaction_processing_test_context(async_db_session)
    initial = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-source-fx-correction-initial",
        correlation_id="corr-source-fx-correction",
    )
    corrected = event.model_copy(update={"transaction_fx_rate": Decimal("2.5")})
    async with context.session_factory() as persistence_session:
        await persistence_session.execute(
            update(DBTransaction)
            .where(DBTransaction.transaction_id == transaction_id)
            .values(transaction_fx_rate=Decimal("2.5"), transaction_fx_rate_origin="SOURCE_BOOKED")
        )
        await persistence_session.commit()

    correction = await process_booked_transaction(
        context=context,
        event=corrected,
        event_id="transactions.persisted-0-source-fx-correction-repair-1",
        correlation_id="corr-source-fx-correction",
        processing_intent=TransactionProcessingIntent.REPAIR,
        repair_delivery_id="source-fx-correction-2.5",
    )
    duplicate = await process_booked_transaction(
        context=context,
        event=corrected,
        event_id="transactions.persisted-0-source-fx-correction-repair-2",
        correlation_id="corr-source-fx-correction",
        processing_intent=TransactionProcessingIntent.REPAIR,
        repair_delivery_id="source-fx-correction-2.5",
    )

    assert initial.status is TransactionProcessingStatus.PROCESSED
    assert correction.status is TransactionProcessingStatus.PROCESSED
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE
    async with context.session_factory() as verification_session:
        lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == transaction_id
                )
            )
        ).scalar_one()
    assert lot.lot_cost_base == Decimal("2500")


async def test_normalized_same_date_fx_duplicates_use_one_repository_order_winner(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-NORMALIZED-FX-TIE-01"
    security_id = "FO_EQ_NORMALIZED_FX_TIE_01"
    cash_id = "CASH-XTS-NORMALIZED-FX-TIE-01"
    transaction_id = "BUY-NORMALIZED-FX-TIE-01"
    transaction_date = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="Normalized FX tie equity",
                isin="SG000000FXT1",
                currency="XTS",
            ),
            instrument_record(
                cash_id,
                name="Normalized FX tie cash",
                isin="CASHXTSFXT01",
                currency="XTS",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=portfolio_id,
                security_id=cash_id,
                display_name="Normalized FX tie cash",
                account_currency="XTS",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
            FxRate(
                from_currency="XTS",
                to_currency="USD",
                rate_date=date(2026, 4, 9),
                rate=Decimal("2.0"),
            ),
            FxRate(
                from_currency="xts",
                to_currency="usd",
                rate_date=date(2026, 4, 9),
                rate=Decimal("2.5"),
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=transaction_date,
        settlement_date=transaction_date,
        transaction_type="BUY",
        quantity="10",
        price="10",
        gross_amount="100",
        trade_currency="XTS",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=cash_id,
    )

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-normalized-fx-tie",
        correlation_id="corr-normalized-fx-tie",
    )

    assert result.status is TransactionProcessingStatus.PROCESSED
    cash_leg_id = f"{transaction_id}-CASHLEG"
    async with context.session_factory() as verification_session:
        rows = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id.in_([transaction_id, cash_leg_id])
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
    assert rows[transaction_id].transaction_fx_rate == Decimal("2.5")
    assert rows[cash_leg_id].transaction_fx_rate == Decimal("2.5")
    assert rows[transaction_id].net_cost == Decimal("250")
    assert rows[cash_leg_id].net_cost == Decimal("-250")


async def test_correction_neutralizes_generated_foreign_cash_basis(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-FUNDED-CASH-NEUTRALIZE-01"
    security_id = "FO_EQ_FUNDED_CASH_NEUTRALIZE_01"
    cash_id = "CASH-XTS-FUNDED-NEUTRALIZE-01"
    transaction_id = "DIV-FUNDED-CASH-NEUTRALIZE-01"
    transaction_date = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="Funded cash neutralization equity",
                isin="SG000000FXN1",
                currency="XTS",
            ),
            instrument_record(
                cash_id,
                name="Funded cash neutralization account",
                isin="CASHXTSFXN01",
                currency="XTS",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=portfolio_id,
                security_id=cash_id,
                display_name="Funded cash neutralization account",
                account_currency="XTS",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
        ]
    )
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=transaction_date,
        settlement_date=transaction_date,
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="100",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=cash_id,
    )
    context = transaction_processing_test_context(async_db_session)
    initial = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-funded-cash-initial",
        correlation_id="corr-funded-cash-neutralize",
    )
    corrected = event.model_copy(
        update={
            "cash_entry_mode": None,
            "settlement_cash_account_id": None,
            "settlement_cash_instrument_id": None,
        }
    )
    async with context.session_factory() as persistence_session:
        await persistence_session.execute(
            update(DBTransaction)
            .where(DBTransaction.transaction_id == transaction_id)
            .values(
                cash_entry_mode=None,
                external_cash_transaction_id=None,
                settlement_cash_account_id=None,
                settlement_cash_instrument_id=None,
            )
        )
        await persistence_session.commit()

    correction = await process_booked_transaction(
        context=context,
        event=corrected,
        event_id="transactions.persisted-0-funded-cash-repair",
        correlation_id="corr-funded-cash-neutralize",
        processing_intent=TransactionProcessingIntent.REPAIR,
    )

    assert initial.status is TransactionProcessingStatus.PROCESSED
    assert correction.status is TransactionProcessingStatus.PROCESSED
    cash_leg_id = f"{transaction_id}-CASHLEG"
    async with context.session_factory() as verification_session:
        cash_leg = (
            await verification_session.execute(
                select(DBTransaction).where(DBTransaction.transaction_id == cash_leg_id)
            )
        ).scalar_one()
        latest_cash_position = (
            await verification_session.execute(
                select(PositionHistory)
                .where(PositionHistory.transaction_id == cash_leg_id)
                .order_by(PositionHistory.id.desc())
                .limit(1)
            )
        ).scalar_one()
    assert cash_leg.gross_transaction_amount == Decimal(0)
    assert cash_leg.gross_cost == Decimal(0)
    assert cash_leg.net_cost == Decimal(0)
    assert cash_leg.net_cost_local == Decimal(0)
    assert cash_leg.transaction_fx_rate == Decimal("2.0")
    assert cash_leg.transaction_fx_rate_origin == "SOURCE_BOOKED"
    assert latest_cash_position.cost_basis == Decimal(0)


async def test_generated_cash_boundary_precision_persists_and_replays(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-FX-PRECISION-01"
    security_id = "FO_EQ_FX_PRECISION_01"
    cash_id = "CASH-XTS-FX-PRECISION-01"
    transaction_id = "DIV-FX-PRECISION-01"
    transaction_date = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="FX precision equity",
                isin="SG000000FXP1",
                currency="XTS",
            ),
            instrument_record(
                cash_id,
                name="FX precision cash",
                isin="CASHXTSFXP01",
                currency="XTS",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=portfolio_id,
                security_id=cash_id,
                display_name="FX precision cash",
                account_currency="XTS",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
        ]
    )
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=transaction_date,
        settlement_date=transaction_date,
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="1.1234567890",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("1.1234567890"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=cash_id,
    )
    context = transaction_processing_test_context(async_db_session)
    initial = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id="transactions.persisted-0-fx-precision",
        correlation_id="corr-fx-precision",
    )
    replay = await process_booked_transaction(
        context=context,
        event=event,
        event_id="transactions.persisted-0-fx-precision-replay",
        correlation_id="corr-fx-precision",
    )

    assert initial.status is TransactionProcessingStatus.PROCESSED
    assert replay.status is TransactionProcessingStatus.DUPLICATE
    async with context.session_factory() as verification_session:
        cash_leg = (
            await verification_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == f"{transaction_id}-CASHLEG"
                )
            )
        ).scalar_one()
    assert cash_leg.net_cost_local == Decimal("1.1234567890")
    assert cash_leg.net_cost == Decimal("1.2621551568")


async def test_same_currency_supplied_fx_must_be_one(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-SAME-CCY-FX-01"
    security_id = "FO_EQ_SAME_CCY_FX_01"
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Same currency FX control",
            isin="SG000000FXS1",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)
    invalid = booked_transaction_event(
        transaction_id="BUY-SAME-CCY-FX-BAD-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="1",
        price="100",
        gross_amount="100",
        trade_currency="USD",
        transaction_fx_rate=Decimal("2"),
    )

    with pytest.raises(TransactionProcessingRejected) as raised:
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=invalid,
            event_id="transactions.persisted-0-same-ccy-fx-bad",
            correlation_id="corr-same-ccy-fx",
        )
    assert raised.value.reason_code == "same_currency_fx_rate_invalid"
    assert raised.value.retryable is False
    async with context.session_factory() as cleanup_session:
        await cleanup_session.execute(
            delete(DBTransaction).where(DBTransaction.transaction_id == invalid.transaction_id)
        )
        await cleanup_session.commit()

    valid = booked_transaction_event(
        transaction_id="BUY-SAME-CCY-FX-ONE-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="1",
        price="100",
        gross_amount="100",
        trade_currency="USD",
        transaction_fx_rate=Decimal("1"),
    )
    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=valid,
        event_id="transactions.persisted-0-same-ccy-fx-one",
        correlation_id="corr-same-ccy-fx",
    )
    assert result.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as verification_session:
        lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == valid.transaction_id
                )
            )
        ).scalar_one()
    assert lot.lot_cost_base == Decimal("100")


async def test_generated_cash_rejects_currency_mismatch_when_mode_defaults_to_auto_generate(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-CASH-CCY-MISMATCH-01"
    security_id = "FO_EQ_CASH_CCY_MISMATCH_01"
    cash_id = "CASH-USD-CASH-CCY-MISMATCH-01"
    transaction_id = "DIVIDEND-CASH-CCY-MISMATCH-01"
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="Cash currency mismatch equity",
                isin="SG000000FXM1",
                currency="XTS",
            ),
            instrument_record(
                cash_id,
                name="USD mismatch cash account",
                isin="CASHUSDFXM01",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=portfolio_id,
                security_id=cash_id,
                display_name="USD settlement cash",
                account_currency="USD",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
        ]
    )
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="100",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("2"),
        cash_entry_mode=None,
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=cash_id,
    )
    context = transaction_processing_test_context(async_db_session)

    with pytest.raises(TransactionProcessingRejected) as raised:
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=event,
            event_id="transactions.persisted-0-cash-ccy-mismatch",
            correlation_id="corr-cash-ccy-mismatch",
        )

    assert raised.value.reason_code == "settlement_cash_currency_mismatch"
    assert raised.value.retryable is False
    async with context.session_factory() as verification_session:
        generated_child = (
            await verification_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == f"{transaction_id}-CASHLEG"
                )
            )
        ).scalar_one_or_none()
    assert generated_child is None


async def test_generated_cash_missing_instrument_reference_is_retryable(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-CASH-REF-MISSING-01"
    security_id = "FO_EQ_CASH_REF_MISSING_01"
    transaction_id = "BUY-CASH-REF-MISSING-01"
    missing_cash_id = "CASH-MISSING-01"
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Missing cash reference equity",
            isin="SG000000FXR1",
            currency="XTS",
        )
    )
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="1",
        price="100",
        gross_amount="100",
        trade_currency="XTS",
        transaction_fx_rate=Decimal("2"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id=missing_cash_id,
        settlement_cash_instrument_id=missing_cash_id,
    )
    context = transaction_processing_test_context(async_db_session)

    with pytest.raises(TransactionProcessingError) as raised:
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=event,
            event_id="transactions.persisted-0-cash-ref-missing",
            correlation_id="corr-cash-ref-missing",
        )

    assert raised.value.reason_code == "cost_dependency_unavailable"
    assert raised.value.retryable is True
    assert raised.value.detail["dependency_error"] == "cash_account_mapping"
    async with context.session_factory() as verification_session:
        generated_child = (
            await verification_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == f"{transaction_id}-CASHLEG"
                )
            )
        ).scalar_one_or_none()
    assert generated_child is None


@pytest.mark.parametrize(
    ("supplied_instrument", "account_currency", "instrument_type", "reason_code"),
    [
        (
            "CASH-USD-DIFFERENT-01",
            "USD",
            "CASH",
            "settlement_cash_instrument_mapping_mismatch",
        ),
        (
            None,
            "EUR",
            "CASH",
            "settlement_cash_account_currency_mismatch",
        ),
        (
            None,
            "USD",
            "EQUITY",
            "settlement_cash_instrument_not_cash",
        ),
    ],
)
async def test_generated_cash_rejects_inconsistent_account_mapping_before_child_write(
    clean_db,
    async_db_session: AsyncSession,
    supplied_instrument: str | None,
    account_currency: str,
    instrument_type: str,
    reason_code: str,
) -> None:
    suffix = reason_code.rsplit("_", 1)[-1].upper()
    portfolio_id = f"PORT-CASH-MAP-{suffix}-01"
    security_id = f"FO_EQ_CASH_MAP_{suffix}_01"
    cash_id = f"CASH-USD-MAP-{suffix}-01"
    transaction_id = f"DIV-CASH-MAP-{suffix}-01"
    async_db_session.add(portfolio_record(portfolio_id, base_currency="USD"))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="Cash mapping control equity",
                isin=f"SGMAP{suffix:0<7}"[:12],
                currency="USD",
            ),
            instrument_record(
                cash_id,
                name="Mapped settlement instrument",
                isin=f"CAMAP{suffix:0<7}"[:12],
                currency="USD",
                product_type=instrument_type,
                asset_class="Cash" if instrument_type == "CASH" else "Equity",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=portfolio_id,
                security_id=cash_id,
                display_name="Mapped settlement account",
                account_currency=account_currency,
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
        ]
    )
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="100",
        trade_currency="USD",
        cash_entry_mode=None,
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=supplied_instrument,
    )
    context = transaction_processing_test_context(async_db_session)

    with pytest.raises(TransactionProcessingRejected) as raised:
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=event,
            event_id=f"transactions.persisted-0-cash-map-{suffix.lower()}",
            correlation_id="corr-cash-map-rejection",
        )

    assert raised.value.reason_code == reason_code
    assert raised.value.retryable is False
    async with context.session_factory() as verification_session:
        generated_child = (
            await verification_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == f"{transaction_id}-CASHLEG"
                )
            )
        ).scalar_one_or_none()
    assert generated_child is None


async def test_generated_cash_account_mapping_is_portfolio_and_tenant_scoped(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-CASH-MAP-SCOPE-01"
    other_portfolio_id = "PORT-CASH-MAP-SCOPE-02"
    security_id = "FO_EQ_CASH_MAP_SCOPE_01"
    cash_id = "CASH-USD-MAP-SCOPE-01"
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, base_currency="USD"),
            portfolio_record(other_portfolio_id, base_currency="USD"),
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                security_id,
                name="Cash map scope equity",
                isin="SGMAPSCOPE01",
                currency="USD",
            ),
            instrument_record(
                cash_id,
                name="Other portfolio cash",
                isin="CAMAPSCOPE01",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            CashAccountMaster(
                cash_account_id=cash_id,
                portfolio_id=other_portfolio_id,
                security_id=cash_id,
                display_name="Other portfolio cash",
                account_currency="USD",
                lifecycle_status="ACTIVE",
                opened_on=date(2026, 1, 1),
            ),
        ]
    )
    event = booked_transaction_event(
        transaction_id="DIV-CASH-MAP-SCOPE-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="100",
        trade_currency="USD",
        cash_entry_mode=None,
        settlement_cash_account_id=cash_id,
        settlement_cash_instrument_id=None,
    )
    context = transaction_processing_test_context(async_db_session)

    with pytest.raises(TransactionProcessingError) as raised:
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=event,
            event_id="transactions.persisted-0-cash-map-scope",
            correlation_id="corr-cash-map-scope",
        )

    assert raised.value.reason_code == "cost_dependency_unavailable"
    assert raised.value.retryable is True
