"""Prove canonical fixed-income redemption booking, settlement, and lot evidence."""

import runpy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import (
    Cashflow,
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    PositionLotState,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayStatus,
    ReplayBookedTransactionCommand,
    TransactionProcessingIntent,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.runtime.dependency_composition import (  # noqa: E501
    build_replay_booked_transaction_use_case,
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

REDEMPTION_CASHFLOW_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c149b2c3d516_feat_add_redemption_cashflow_rules.py"
)


@pytest.fixture
def redemption_cashflow_rules(clean_db, db_engine) -> None:
    """Apply the branch rule migration when the cached integration image predates it."""

    with db_engine.begin() as connection:
        rule_count = connection.execute(
            text(
                """
                SELECT count(*)
                FROM cashflow_rules
                WHERE transaction_type IN (
                    'MATURITY_REDEMPTION',
                    'CALL_REDEMPTION',
                    'PARTIAL_REDEMPTION'
                )
                """
            )
        ).scalar_one()
        if rule_count == 3:
            return
        migration = runpy.run_path(str(REDEMPTION_CASHFLOW_MIGRATION))
        migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
        migration["upgrade"]()


class _CapturingReplayProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def publish_message(
        self,
        *,
        topic: str,
        key: str,
        value: dict[str, Any],
        headers: list[tuple[str, bytes]],
    ) -> None:
        self.messages.append({"topic": topic, "key": key, "value": value, "headers": headers})

    def flush(self) -> int:
        return 0


@pytest.mark.parametrize(
    (
        "transaction_type",
        "redeemed_quantity",
        "accrued_interest",
        "expected_residual_quantity",
        "expected_consumed_basis",
        "expected_residual_basis",
        "expected_capital_pnl",
        "expected_settlement",
        "factor_fields",
    ),
    [
        (
            "MATURITY_REDEMPTION",
            "100",
            "5",
            "0",
            "97",
            "0",
            "3",
            "105",
            {},
        ),
        (
            "CALL_REDEMPTION",
            "100",
            "4",
            "0",
            "97",
            "0",
            "3",
            "104",
            {},
        ),
        (
            "PARTIAL_REDEMPTION",
            "40",
            "2",
            "60",
            "38.8",
            "58.2",
            "1.2",
            "42",
            {"old_factor": Decimal("1"), "new_factor": Decimal("0.6")},
        ),
    ],
)
async def test_redemption_books_linked_principal_cash_and_immutable_lot_evidence(
    clean_db,
    redemption_cashflow_rules,
    async_db_session: AsyncSession,
    transaction_type: str,
    redeemed_quantity: str,
    accrued_interest: str,
    expected_residual_quantity: str,
    expected_consumed_basis: str,
    expected_residual_basis: str,
    expected_capital_pnl: str,
    expected_settlement: str,
    factor_fields: dict[str, Decimal],
) -> None:
    suffix = transaction_type.removesuffix("_REDEMPTION")
    portfolio_id = f"PORT-REDEMPTION-{suffix}-01"
    security_id = f"FO_FI_REDEMPTION_{suffix}_01"
    buy_id = f"BUY-REDEMPTION-{suffix}-01"
    redemption_id = f"{transaction_type}-01"
    interest_leg_id = f"{redemption_id}-ACCRUED-INTEREST"
    cash_leg_id = f"{redemption_id}-CASHLEG"

    acquisition = booked_transaction_event(
        transaction_id=buy_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="0.97",
        gross_amount="97",
    )
    redemption = booked_transaction_event(
        transaction_id=redemption_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=redeemed_quantity,
        price="1",
        gross_amount=redeemed_quantity,
        redemption_price_type="PAR",
        principal_proceeds_local=Decimal(redeemed_quantity),
        accrued_interest_proceeds_local=Decimal(accrued_interest),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-REDEMPTION-01",
        settlement_cash_instrument_id="CASH-USD",
        **factor_fields,
    )

    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name=f"{suffix.title()} Redemption Note",
                isin=f"SG0000{suffix[:4]:0<4}01",
                currency="USD",
                product_type="BOND",
                asset_class="FIXED_INCOME",
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)

    acquisition_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=acquisition,
        event_id=f"transactions.persisted-0-buy-{suffix.lower()}",
        correlation_id=f"corr-buy-{suffix.lower()}",
    )
    redemption_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=redemption,
        event_id=f"transactions.persisted-0-redemption-{suffix.lower()}",
        correlation_id=f"corr-redemption-{suffix.lower()}",
    )
    duplicate = await process_booked_transaction(
        context=context,
        event=redemption,
        event_id=f"transactions.persisted-0-redemption-{suffix.lower()}",
        correlation_id=f"corr-redemption-{suffix.lower()}",
    )

    assert acquisition_result.status is TransactionProcessingStatus.PROCESSED
    assert redemption_result.status is TransactionProcessingStatus.PROCESSED
    assert redemption_result.processed_transaction_ids == (
        redemption_id,
        interest_leg_id,
        cash_leg_id,
    )
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        transactions = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id.in_(
                                [redemption_id, interest_leg_id, cash_leg_id]
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        source_lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.portfolio_id == portfolio_id,
                    PositionLotState.source_transaction_id == buy_id,
                )
            )
        ).scalar_one()
        receipt = (
            await verification_session.execute(
                select(LotDisposalReceiptRecord).where(
                    LotDisposalReceiptRecord.disposal_transaction_id == redemption_id
                )
            )
        ).scalar_one()
        allocations = (
            (
                await verification_session.execute(
                    select(LotDisposalAllocationRecord)
                    .where(
                        LotDisposalAllocationRecord.receipt_id == receipt.receipt_id,
                        LotDisposalAllocationRecord.receipt_version == receipt.receipt_version,
                    )
                    .order_by(LotDisposalAllocationRecord.allocation_ordinal)
                )
            )
            .scalars()
            .all()
        )
        cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(
                        Cashflow.transaction_id.in_([redemption_id, interest_leg_id, cash_leg_id])
                    )
                    .order_by(Cashflow.transaction_id)
                )
            )
            .scalars()
            .all()
        )

    persisted_redemption = transactions[redemption_id]
    assert persisted_redemption.external_cash_transaction_id == cash_leg_id
    assert persisted_redemption.net_cost_local == -Decimal(expected_consumed_basis)
    assert persisted_redemption.allocated_cost_basis_local == Decimal(expected_consumed_basis)
    assert persisted_redemption.realized_capital_pnl_local == Decimal(expected_capital_pnl)
    assert persisted_redemption.realized_fx_pnl_local == Decimal(0)
    assert persisted_redemption.realized_total_pnl_local == Decimal(expected_capital_pnl)

    generated_cash_leg = transactions[cash_leg_id]
    assert generated_cash_leg.transaction_type == "ADJUSTMENT"
    assert generated_cash_leg.gross_transaction_amount == Decimal(expected_settlement)
    assert generated_cash_leg.movement_direction == "INFLOW"
    assert generated_cash_leg.originating_transaction_id == redemption_id

    generated_interest_leg = transactions[interest_leg_id]
    assert generated_interest_leg.transaction_type == "INTEREST"
    assert generated_interest_leg.gross_transaction_amount == Decimal(accrued_interest)
    assert generated_interest_leg.originating_transaction_id == redemption_id
    assert generated_interest_leg.component_type == "REDEMPTION_ACCRUED_INTEREST"

    cashflows_by_transaction = {cashflow.transaction_id: cashflow for cashflow in cashflows}
    assert cashflows_by_transaction[redemption_id].amount == Decimal(redeemed_quantity)
    assert cashflows_by_transaction[redemption_id].classification == "INVESTMENT_INFLOW"
    assert cashflows_by_transaction[interest_leg_id].amount == Decimal(accrued_interest)
    assert cashflows_by_transaction[interest_leg_id].classification == "INCOME"
    assert cashflows_by_transaction[cash_leg_id].amount == Decimal(expected_settlement)
    assert len({cashflow.economic_event_id for cashflow in cashflows}) == 1
    assert len({cashflow.linked_transaction_group_id for cashflow in cashflows}) == 1

    assert source_lot.open_quantity == Decimal(expected_residual_quantity)
    assert source_lot.lot_cost_local == Decimal(expected_residual_basis)
    assert source_lot.lot_cost_base == Decimal(expected_residual_basis)
    assert receipt.transaction_type == transaction_type
    assert receipt.destination_type is None
    assert receipt.consumed_quantity == Decimal(redeemed_quantity)
    assert receipt.consumed_cost_local == Decimal(expected_consumed_basis)
    assert receipt.consumed_cost_base == Decimal(expected_consumed_basis)
    assert [
        (
            allocation.source_transaction_id,
            allocation.consumed_quantity,
            allocation.consumed_cost_local,
            allocation.consumed_cost_base,
        )
        for allocation in allocations
    ] == [
        (
            buy_id,
            Decimal(redeemed_quantity),
            Decimal(expected_consumed_basis),
            Decimal(expected_consumed_basis),
        )
    ]


async def test_partial_redemption_replay_restores_cash_without_versioning_receipt(
    clean_db,
    redemption_cashflow_rules,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-REDEMPTION-REPLAY-01"
    security_id = "FO_FI_REDEMPTION_REPLAY_01"
    redemption_id = "PARTIAL_REDEMPTION-REPLAY-01"
    interest_leg_id = f"{redemption_id}-ACCRUED-INTEREST"
    cash_leg_id = f"{redemption_id}-CASHLEG"
    acquisition = booked_transaction_event(
        transaction_id="BUY-REDEMPTION-REPLAY-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="0.97",
        gross_amount="97",
    )
    redemption = booked_transaction_event(
        transaction_id=redemption_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
        transaction_type="PARTIAL_REDEMPTION",
        quantity="40",
        price="1",
        gross_amount="40",
        redemption_price_type="PAR",
        old_factor=Decimal("1"),
        new_factor=Decimal("0.6"),
        principal_proceeds_local=Decimal("40"),
        accrued_interest_proceeds_local=Decimal("2"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-REDEMPTION-REPLAY-01",
        settlement_cash_instrument_id="CASH-USD",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Replayable Partial Redemption Note",
                isin="SG0000007810",
                currency="USD",
                product_type="BOND",
                asset_class="FIXED_INCOME",
            ),
        ]
    )
    initial_context = transaction_processing_test_context(async_db_session)
    for offset, event in enumerate((acquisition, redemption), start=9901):
        result = await persist_and_process_booked_transaction(
            session=async_db_session,
            context=initial_context,
            event=event,
            event_id=f"transactions.persisted-0-{offset}",
            correlation_id=f"corr-{event.transaction_id.lower()}",
        )
        assert result.status is TransactionProcessingStatus.PROCESSED

    await async_db_session.execute(
        delete(Cashflow).where(
            Cashflow.transaction_id.in_([redemption_id, interest_leg_id, cash_leg_id])
        )
    )
    await async_db_session.commit()

    producer = _CapturingReplayProducer()
    restarted_context = transaction_processing_test_context(async_db_session)
    replay_use_case = build_replay_booked_transaction_use_case(
        session_factory=restarted_context.session_factory,
        kafka_producer=producer,
    )
    replay_result = await replay_use_case.execute(
        ReplayBookedTransactionCommand(
            transaction_id=redemption_id,
            correlation_id="corr-partial-redemption-replay-01",
        )
    )
    replay_event = TransactionEvent.model_validate(producer.messages[0]["value"])
    repair_result = await process_booked_transaction(
        context=restarted_context,
        event=replay_event,
        event_id="transactions.persisted-0-9903",
        correlation_id="corr-partial-redemption-replay-01",
        processing_intent=TransactionProcessingIntent.REPAIR,
    )

    assert replay_result.status is BookedTransactionReplayStatus.REPLAYED
    assert replay_event.redemption_price_type == "PAR"
    assert replay_event.old_factor == Decimal("1")
    assert replay_event.new_factor == Decimal("0.6")
    assert replay_event.principal_proceeds_local == Decimal("40")
    assert replay_event.accrued_interest_proceeds_local == Decimal("2")
    assert replay_event.external_cash_transaction_id == cash_leg_id
    assert repair_result.status is TransactionProcessingStatus.PROCESSED
    assert repair_result.processed_transaction_ids == (
        redemption_id,
        interest_leg_id,
        cash_leg_id,
    )

    async with restarted_context.session_factory() as verification_session:
        cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(
                        Cashflow.transaction_id.in_([redemption_id, interest_leg_id, cash_leg_id])
                    )
                    .order_by(Cashflow.transaction_id)
                )
            )
            .scalars()
            .all()
        )
        receipts = (
            (
                await verification_session.execute(
                    select(LotDisposalReceiptRecord).where(
                        LotDisposalReceiptRecord.disposal_transaction_id == redemption_id
                    )
                )
            )
            .scalars()
            .all()
        )
        allocation_count = await verification_session.scalar(
            select(func.count())
            .select_from(LotDisposalAllocationRecord)
            .where(
                LotDisposalAllocationRecord.receipt_id == receipts[0].receipt_id,
                LotDisposalAllocationRecord.receipt_version == receipts[0].receipt_version,
            )
        )

    cashflows_by_transaction = {cashflow.transaction_id: cashflow for cashflow in cashflows}
    assert cashflows_by_transaction[redemption_id].amount == Decimal("40")
    assert cashflows_by_transaction[redemption_id].classification == "INVESTMENT_INFLOW"
    assert cashflows_by_transaction[interest_leg_id].amount == Decimal("2")
    assert cashflows_by_transaction[interest_leg_id].classification == "INCOME"
    assert cashflows_by_transaction[cash_leg_id].amount == Decimal("42")
    assert len({cashflow.economic_event_id for cashflow in cashflows}) == 1
    assert len({cashflow.linked_transaction_group_id for cashflow in cashflows}) == 1
    assert len(receipts) == 1
    assert allocation_count == 1
