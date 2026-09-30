import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import OutboxEvent, Portfolio, ProcessedEvent, Transaction
from portfolio_common.domain.transaction import build_transaction_payload_identity
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import TransactionSemanticConflictError
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.persistence_service.app.consumers import base_consumer as base_consumer_module
from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)
from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)
from tests.test_support.tenant import TEST_TENANT_ID

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
            tenant_id=TEST_TENANT_ID,
            legal_book_id="BOOK_BOUNDARY_01",
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


@pytest.mark.lifecycle
async def test_transaction_consumer_boundary_persists_transaction_outbox_and_idempotency(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def current_test_session() -> AsyncIterator[AsyncSession]:
        async with async_factory() as session:
            yield session

    monkeypatch.setattr(
        base_consumer_module,
        "get_async_db_session",
        current_test_session,
    )
    await _seed_portfolio(async_db_session)
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
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

    # Retention can remove the short-lived processed-event claim while the
    # immutable transaction row remains.  The durable ledger replay must still
    # be a complete no-op, including outbox publication.
    await async_db_session.execute(
        delete(ProcessedEvent).where(
            ProcessedEvent.event_id == "TXN_BOUNDARY_01",
            ProcessedEvent.service_name == "persistence-transactions",
        )
    )
    await async_db_session.commit()

    await consumer.process_message(_FakeMessage(_transaction_payload(), offset=3))

    outbox_count_after_expired_claim_replay = (
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
    assert outbox_count_after_expired_claim_replay == 1


@pytest.mark.lifecycle
async def test_transaction_consumer_rejects_conflicting_source_booked_fx_redelivery(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def current_test_session() -> AsyncIterator[AsyncSession]:
        async with async_factory() as session:
            yield session

    monkeypatch.setattr(base_consumer_module, "get_async_db_session", current_test_session)
    await _seed_portfolio(async_db_session)
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        topic="raw-transactions",
        group_id="persistence-boundary-booked-fx-tests",
        dlq_topic=None,
    )
    original = {
        **_transaction_payload("TXN_BOUNDARY_FX_01"),
        "transaction_fx_rate": "2.0",
        "transaction_fx_rate_origin": "producer-cannot-assert-authority",
    }

    await consumer.process_message(_FakeMessage(original, offset=1))
    await consumer.process_message(_FakeMessage({**original}, offset=2))

    with pytest.raises(TransactionSemanticConflictError):
        await consumer.process_message(
            _FakeMessage({**original, "transaction_fx_rate": "2.5"}, offset=3)
        )

    persisted = await async_db_session.scalar(
        select(Transaction).where(Transaction.transaction_id == "TXN_BOUNDARY_FX_01")
    )
    assert persisted is not None
    assert persisted.transaction_fx_rate == 2
    assert persisted.transaction_fx_rate_origin == "SOURCE_BOOKED"


@pytest.mark.lifecycle
async def test_late_v1_writer_and_v2_consumer_complete_without_lock_order_deadlock(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def current_test_session() -> AsyncIterator[AsyncSession]:
        async with async_factory() as session:
            yield session

    monkeypatch.setattr(base_consumer_module, "get_async_db_session", current_test_session)
    await _seed_portfolio(async_db_session)
    legacy_payload = {
        **_transaction_payload("TXN_BOUNDARY_LATE_V1"),
        "transaction_fx_rate": "2.0",
        "transaction_fx_rate_origin": None,
        "tenant_id": TEST_TENANT_ID,
    }
    legacy_event = TransactionEvent.model_validate(legacy_payload)
    legacy_identity = build_transaction_payload_identity(
        legacy_event.model_dump(mode="python"), tenant_id=TEST_TENANT_ID
    )

    async with async_factory() as legacy_session:
        assert await IdempotencyRepository(legacy_session).claim_semantic_event_processing(
            event_id=legacy_event.transaction_id,
            portfolio_id=legacy_event.portfolio_id,
            service_name="persistence-transactions",
            semantic_key=legacy_identity.semantic_key,
            payload_fingerprint=legacy_identity.payload_fingerprint,
            correlation_id="corr-late-v1",
            tenant_id=TEST_TENANT_ID,
        )
        await TransactionDBRepository(legacy_session).create_or_update_transaction(legacy_event)

        consumer = TransactionPersistenceConsumer(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            topic="raw-transactions",
            group_id="persistence-boundary-rolling-version-tests",
            dlq_topic=None,
        )
        v2_payload = {
            **legacy_payload,
            "transaction_fx_rate_origin": "SOURCE_BOOKED",
        }
        v2_task = asyncio.create_task(consumer.process_message(_FakeMessage(v2_payload, offset=2)))
        await asyncio.sleep(0.2)
        assert not v2_task.done(), "v2 consumer did not wait for the late v1 durable claim"
        await legacy_session.commit()
        await asyncio.wait_for(v2_task, timeout=5)

    persisted = await async_db_session.scalar(
        select(Transaction).where(Transaction.transaction_id == "TXN_BOUNDARY_LATE_V1")
    )
    assert persisted is not None
    assert persisted.transaction_fx_rate == 2
    assert persisted.transaction_fx_rate_origin is None


@pytest.mark.lifecycle
async def test_legacy_compatibility_serializes_with_concurrent_authorized_correction(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def current_test_session() -> AsyncIterator[AsyncSession]:
        async with async_factory() as session:
            yield session

    monkeypatch.setattr(base_consumer_module, "get_async_db_session", current_test_session)
    await _seed_portfolio(async_db_session)
    legacy_payload = {
        **_transaction_payload("TXN_BOUNDARY_LEGACY_RACE"),
        "transaction_fx_rate": "2.0",
        "transaction_fx_rate_origin": None,
        "tenant_id": TEST_TENANT_ID,
    }
    legacy_event = TransactionEvent.model_validate(legacy_payload)
    legacy_identity = build_transaction_payload_identity(
        legacy_event.model_dump(mode="python"), tenant_id=TEST_TENANT_ID
    )
    async with async_factory() as setup_session:
        await IdempotencyRepository(setup_session).claim_semantic_event_processing(
            event_id=legacy_event.transaction_id,
            portfolio_id=legacy_event.portfolio_id,
            service_name="persistence-transactions",
            semantic_key=legacy_identity.semantic_key,
            payload_fingerprint=legacy_identity.payload_fingerprint,
            correlation_id="corr-legacy-race",
            tenant_id=TEST_TENANT_ID,
        )
        await TransactionDBRepository(setup_session).create_or_update_transaction(legacy_event)
        await setup_session.commit()

    consumer = TransactionPersistenceConsumer(
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        topic="raw-transactions",
        group_id="persistence-boundary-legacy-race-tests",
        dlq_topic=None,
    )
    incoming = {**legacy_payload, "transaction_fx_rate_origin": "SOURCE_BOOKED"}
    corrected = TransactionEvent.model_validate({**incoming, "transaction_fx_rate": "2.5"})
    corrected_identity = build_transaction_payload_identity(
        corrected.model_dump(mode="python"), tenant_id=TEST_TENANT_ID
    )

    async with async_factory() as correction_session:
        await correction_session.execute(
            text(
                "UPDATE transactions SET transaction_fx_rate = 2.5, "
                "transaction_fx_rate_origin = 'SOURCE_BOOKED', payload_fingerprint = :fingerprint "
                "WHERE transaction_id = 'TXN_BOUNDARY_LEGACY_RACE'"
            ),
            {"fingerprint": corrected_identity.payload_fingerprint},
        )
        replay_task = asyncio.create_task(
            consumer.process_message(_FakeMessage(incoming, offset=2))
        )
        await asyncio.sleep(0.2)
        assert not replay_task.done(), "compatibility check did not wait for transaction lock"
        await correction_session.commit()
        with pytest.raises(TransactionSemanticConflictError):
            await asyncio.wait_for(replay_task, timeout=5)

    persisted = await async_db_session.scalar(
        select(Transaction).where(Transaction.transaction_id == "TXN_BOUNDARY_LEGACY_RACE")
    )
    assert persisted is not None
    assert persisted.transaction_fx_rate == 2.5
    assert persisted.transaction_fx_rate_origin == "SOURCE_BOOKED"


@pytest.mark.lifecycle
@pytest.mark.parametrize("invalid_fence", ["portfolio_scope", "fingerprint"])
async def test_legacy_compatibility_rejects_inconsistent_physical_fence(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    invalid_fence: str,
) -> None:
    async_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def current_test_session() -> AsyncIterator[AsyncSession]:
        async with async_factory() as session:
            yield session

    monkeypatch.setattr(base_consumer_module, "get_async_db_session", current_test_session)
    await _seed_portfolio(async_db_session)
    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            legal_book_id="BOOK_BOUNDARY_OTHER",
            portfolio_id="PORT_BOUNDARY_OTHER",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="High",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CIF_BOUNDARY_OTHER",
            status="ACTIVE",
        )
    )
    await async_db_session.commit()

    legacy_payload = {
        **_transaction_payload("TXN_BOUNDARY_INVALID_FENCE"),
        "transaction_fx_rate": "2.0",
        "transaction_fx_rate_origin": None,
        "tenant_id": TEST_TENANT_ID,
    }
    legacy_event = TransactionEvent.model_validate(legacy_payload)
    legacy_identity = build_transaction_payload_identity(
        legacy_event.model_dump(mode="python"), tenant_id=TEST_TENANT_ID
    )
    await TransactionDBRepository(async_db_session).create_or_update_transaction(legacy_event)
    await async_db_session.commit()

    fence_portfolio_id = (
        "PORT_BOUNDARY_OTHER" if invalid_fence == "portfolio_scope" else "PORT_BOUNDARY_01"
    )
    fence_fingerprint = (
        "sha256:" + "f" * 64
        if invalid_fence == "fingerprint"
        else legacy_identity.payload_fingerprint
    )
    await IdempotencyRepository(async_db_session).claim_semantic_event_processing(
        event_id=legacy_event.transaction_id,
        portfolio_id=fence_portfolio_id,
        service_name="persistence-transactions",
        semantic_key=legacy_identity.semantic_key,
        payload_fingerprint=fence_fingerprint,
        correlation_id="corr-invalid-fence",
        tenant_id=TEST_TENANT_ID,
    )
    await async_db_session.commit()

    consumer = TransactionPersistenceConsumer(
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        topic="raw-transactions",
        group_id=f"persistence-boundary-invalid-{invalid_fence}",
        dlq_topic=None,
    )
    with pytest.raises(TransactionSemanticConflictError):
        await consumer.process_message(
            _FakeMessage(
                {**legacy_payload, "transaction_fx_rate_origin": "SOURCE_BOOKED"},
                offset=2,
            )
        )
