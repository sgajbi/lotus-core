from datetime import UTC, date, datetime
from time import perf_counter

import pytest
from portfolio_common.database_models import Cashflow, Portfolio, Transaction, TransactionCost
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.application.transaction_query import TransactionLedgerFilters
from src.services.query_service.app.repositories.transaction_repository import TransactionRepository
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.performance]

TRANSACTION_COUNT = 100_000
BATCH_SIZE = 5_000


async def test_transaction_ledger_input_evidence_is_bounded_at_bank_day_volume(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await async_db_session.execute(
        insert(Portfolio),
        [
            {
                "portfolio_id": "PORT-LEDGER-CAPACITY",
                "tenant_id": TEST_TENANT_ID,
                "base_currency": "USD",
                "open_date": date(2024, 1, 1),
                "risk_exposure": "BALANCED",
                "investment_time_horizon": "LONG_TERM",
                "portfolio_type": "ADVISORY",
                "booking_center_code": "SG",
                "client_id": "CLIENT-LEDGER-CAPACITY",
                "status": "ACTIVE",
            }
        ],
    )
    for start in range(0, TRANSACTION_COUNT, BATCH_SIZE):
        stop = min(start + BATCH_SIZE, TRANSACTION_COUNT)
        transaction_ids = [f"TX-CAPACITY-{sequence:06d}" for sequence in range(start, stop)]
        await async_db_session.execute(
            insert(Transaction),
            [
                {
                    "transaction_id": transaction_id,
                    "portfolio_id": "PORT-LEDGER-CAPACITY",
                    "instrument_id": f"INST-{sequence % 500:04d}",
                    "security_id": f"SEC-{sequence % 500:04d}",
                    "transaction_type": "BUY",
                    "quantity": "10",
                    "price": "100",
                    "gross_transaction_amount": "1000",
                    "trade_currency": "USD",
                    "currency": "USD",
                    "transaction_date": datetime(2026, 1, 2, tzinfo=UTC),
                }
                for sequence, transaction_id in zip(
                    range(start, stop),
                    transaction_ids,
                    strict=True,
                )
            ],
        )
        await async_db_session.execute(
            insert(TransactionCost),
            [
                {
                    "transaction_id": transaction_id,
                    "fee_type": "BROKERAGE",
                    "amount": "1",
                    "currency": "USD",
                }
                for transaction_id in transaction_ids
            ],
        )
        await async_db_session.execute(
            insert(Cashflow),
            [
                {
                    "transaction_id": transaction_id,
                    "portfolio_id": "PORT-LEDGER-CAPACITY",
                    "security_id": f"SEC-{sequence % 500:04d}",
                    "cashflow_date": date(2026, 1, 2),
                    "epoch": 1,
                    "amount": "-1001",
                    "currency": "USD",
                    "classification": "TRADE_SETTLEMENT",
                    "timing": "SETTLED",
                    "calculation_type": "TRANSACTION_DERIVED",
                    "is_position_flow": True,
                    "is_portfolio_flow": False,
                }
                for sequence, transaction_id in zip(
                    range(start, stop),
                    transaction_ids,
                    strict=True,
                )
            ],
        )
        await async_db_session.commit()

    started_at = perf_counter()
    evidence = await TransactionRepository(async_db_session).get_transaction_ledger_input_evidence(
        filters=TransactionLedgerFilters(
            portfolio_id="PORT-LEDGER-CAPACITY",
            as_of_date=date(2026, 1, 31),
        ),
        reporting_currency="USD",
        as_of_date=date(2026, 1, 31),
    )
    elapsed_seconds = perf_counter() - started_at

    assert evidence.transaction_count == TRANSACTION_COUNT
    assert len(evidence.transaction_digest or "") == 64
    assert len(evidence.transaction_cost_digest or "") == 64
    assert len(evidence.selected_cashflow_digest or "") == 64
    assert evidence.selected_fx_rate_digest is None
    print(
        "ledger_input_evidence_capacity "
        f"rows={TRANSACTION_COUNT} costs={TRANSACTION_COUNT} cashflows={TRANSACTION_COUNT} "
        f"elapsed_seconds={elapsed_seconds:.3f}"
    )
