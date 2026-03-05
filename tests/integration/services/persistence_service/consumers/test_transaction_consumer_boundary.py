import json
from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import OutboxEvent, Portfolio, ProcessedEvent, Transaction
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)

pytestmark = pytest.mark.asyncio


class _FakeMessage:
    def __init__(self, payload: dict, offset: int = 1) -> None:
        self._payload = payload
        self._offset = offset

    def topic(self) -> str:
        return "raw-transactions"

    def partition(self) -> int:
        return 0

    def offset(self) -> int:
        return self._offset

    def value(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def key(self) -> bytes:
        return self._payload["transaction_id"].encode("utf-8")

    def headers(self):
        return [("correlation_id", b"CID-BOUNDARY-01")]


def _transaction_payload(transaction_id: str = "TXN_BOUNDARY_01") -> dict:
    return {
        "transaction_id": transaction_id,
        "portfolio_id": "PORT_BOUNDARY_01",
        "instrument_id": "INST_BOUNDARY_01",
        "security_id": "SEC_BOUNDARY_01",
        "transaction_date": "2026-03-05T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": "100",
        "price": "10",
        "gross_transaction_amount": "1000",
        "trade_currency": "USD",
        "currency": "USD",
        "economic_event_id": "EVT-BOUNDARY-01",
        "linked_transaction_group_id": "LTG-BOUNDARY-01",
        "calculation_policy_id": "BUY_DEFAULT",
        "calculation_policy_version": "1.0.0",
        "source_system": "OMS",
    }


async def _seed_portfolio(async_db_session: AsyncSession) -> None:
    async_db_session.add(
        Portfolio(
            portfolio_id="PORT_BOUNDARY_01",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="High",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CIF_BOUNDARY_01",
            status="ACTIVE",
        )
    )
    await async_db_session.commit()


async def test_transaction_consumer_boundary_persists_transaction_outbox_and_idempotency(
    clean_db, async_db_session: AsyncSession
) -> None:
    await _seed_portfolio(async_db_session)
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers="localhost:9092",
        topic="raw-transactions",
        group_id="persistence-boundary-tests",
        dlq_topic=None,
    )

    await consumer.process_message(_FakeMessage(_transaction_payload()))

    persisted_txn = (
        await async_db_session.execute(
            select(Transaction).where(Transaction.transaction_id == "TXN_BOUNDARY_01")
        )
    ).scalar_one_or_none()
    assert persisted_txn is not None
    assert persisted_txn.portfolio_id == "PORT_BOUNDARY_01"
    assert persisted_txn.transaction_date == datetime(2026, 3, 5, 10, 0, 0, tzinfo=UTC)
    assert persisted_txn.calculation_policy_version == "1.0.0"

    outbox_count = (
        await async_db_session.execute(
            select(func.count()).select_from(
                select(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == "PORT_BOUNDARY_01",
                    OutboxEvent.event_type == "RawTransactionPersisted",
                )
                .subquery()
            )
        )
    ).scalar_one()
    assert outbox_count == 1

    processed_count = (
        await async_db_session.execute(
            select(func.count()).select_from(
                select(ProcessedEvent)
                .where(
                    ProcessedEvent.event_id == "TXN_BOUNDARY_01",
                    ProcessedEvent.service_name == "persistence-transactions",
                )
                .subquery()
            )
        )
    ).scalar_one()
    assert processed_count == 1
    await consumer.process_message(_FakeMessage(_transaction_payload(), offset=2))
    txn_count_after_replay = (
        await async_db_session.execute(
            select(func.count()).select_from(
                select(Transaction)
                .where(Transaction.transaction_id == "TXN_BOUNDARY_01")
                .subquery()
            )
        )
    ).scalar_one()
    assert txn_count_after_replay == 1

    outbox_count_after_replay = (
        await async_db_session.execute(
            select(func.count()).select_from(
                select(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == "PORT_BOUNDARY_01",
                    OutboxEvent.event_type == "RawTransactionPersisted",
                )
                .subquery()
            )
        )
    ).scalar_one()
    assert outbox_count_after_replay == 1
