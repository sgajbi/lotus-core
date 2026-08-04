"""Prove canonical fixed-income redemption booking, settlement, and lot evidence."""

import runpy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

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
from sqlalchemy import select, text
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
    assert redemption_result.processed_transaction_ids == (redemption_id, cash_leg_id)
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        transactions = {
            row.transaction_id: row
            for row in (
                (
                    await verification_session.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id.in_([redemption_id, cash_leg_id])
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
                    .where(Cashflow.transaction_id.in_([redemption_id, cash_leg_id]))
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
    assert [cashflow.amount for cashflow in cashflows] == [
        Decimal(expected_settlement),
        Decimal(expected_settlement),
    ]
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
