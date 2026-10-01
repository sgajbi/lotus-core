"""Prove negative pre-fee INTEREST refusal in the PostgreSQL processing path."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from portfolio_common.database_models import Cashflow, OutboxEvent, PositionHistory, ProcessedEvent
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from portfolio_common.reprocessing_replay import (
    TRANSACTION_REPLAY_SOURCE_INVALID,
    ReprocessingReplayError,
)
from portfolio_common.reprocessing_repository import ReprocessingRepository
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.ingestion_service.app.DTOs.transaction_dto import Transaction
from src.services.persistence_service.app.consumers import base_consumer as base_consumer_module
from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)
from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.idempotency import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
)
from tests.test_support.tenant import TEST_TENANT_ID
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
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


def _valid_interest_event(
    transaction_id: str = "INTEREST-NEGATIVE-PRE-FEE-001",
) -> TransactionEvent:
    return booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id="PORT-INTEREST-PRE-FEE-001",
        security_id="BOND-INTEREST-PRE-FEE-001",
        transaction_date=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
        transaction_type="INTEREST",
        quantity="0",
        price="0",
        gross_amount="10",
        trade_fee="1",
        withholding_tax_amount=Decimal("2"),
        interest_direction="EXPENSE",
    )


class _RawTransactionMessage:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def topic(self) -> str:
        return "raw-transactions"

    def partition(self) -> int:
        return 0

    def offset(self) -> int:
        return 1175

    def value(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def key(self) -> bytes:
        return str(self._payload["transaction_id"]).encode("utf-8")

    def headers(self) -> list[tuple[str, bytes]]:
        return [("correlation_id", b"corr-interest-negative-pre-fee")]


async def test_negative_pre_fee_interest_has_no_derived_effects_after_restart_retry(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_event = _valid_interest_event()
    invalid_payload = valid_event.model_dump(mode="json")
    invalid_payload.update({"trade_fee": "2", "withholding_tax_amount": "11"})
    valid_payload = valid_event.model_dump(mode="json")
    bond = instrument_record(
        valid_event.security_id,
        name="Private Bank USD Interest Bond",
        isin="US0000011751",
        currency="USD",
        product_type="BOND",
        asset_class="Fixed Income",
    )
    async_db_session.add_all(
        [
            portfolio_record(valid_event.portfolio_id),
            bond,
        ]
    )
    await async_db_session.commit()

    with pytest.raises(ValidationError) as ingress_rejection:
        Transaction.model_validate(invalid_payload)
    assert ingress_rejection.value.errors()[0]["type"] == "INTEREST_018_NEGATIVE_PRE_FEE_NET"

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def current_test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(base_consumer_module, "get_async_db_session", current_test_session)
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        topic="raw-transactions",
        group_id="interest-negative-pre-fee-tests",
        dlq_topic=None,
    )

    for _attempt in range(2):
        with pytest.raises(ValidationError) as persistence_rejection:
            await consumer.process_message(_RawTransactionMessage(invalid_payload))
        assert persistence_rejection.value.errors()[0]["type"] == (
            "INTEREST_018_NEGATIVE_PRE_FEE_NET"
        )

    assert (
        await _source_and_derived_effect_count(
            async_db_session,
            valid_event.transaction_id,
            valid_event.portfolio_id,
        )
        == 0
    )

    await consumer.process_message(_RawTransactionMessage(valid_payload))
    persisted = await async_db_session.scalar(
        select(DBTransaction).where(DBTransaction.transaction_id == valid_event.transaction_id)
    )
    assert persisted is not None
    assert persisted.gross_transaction_amount == Decimal("10")
    assert persisted.withholding_tax_amount == Decimal("2")
    assert persisted.trade_fee == Decimal("1")

    valid_context = transaction_processing_test_context(async_db_session)
    first = await process_booked_transaction(
        context=valid_context,
        event=valid_event,
        event_id="transactions.persisted-0-interest-valid-pre-fee-001",
        correlation_id="corr-interest-valid-pre-fee-1",
    )
    replay_context = transaction_processing_test_context(async_db_session)
    replay = await process_booked_transaction(
        context=replay_context,
        event=valid_event,
        event_id="transactions.persisted-0-interest-valid-pre-fee-001",
        correlation_id="corr-interest-valid-pre-fee-2",
    )

    assert first.status is TransactionProcessingStatus.PROCESSED
    assert replay.status is TransactionProcessingStatus.DUPLICATE
    cashflows = (
        (
            await async_db_session.execute(
                select(Cashflow).where(Cashflow.transaction_id == valid_event.transaction_id)
            )
        )
        .scalars()
        .all()
    )
    assert [cashflow.amount for cashflow in cashflows] == [Decimal("-9")]


async def test_reprocessing_repository_maps_persisted_historical_invalid_interest(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    historical_event = _valid_interest_event("INTEREST-HISTORICAL-INVALID-001")
    historical_record = canonical_transaction_record(historical_event)
    historical_record.withholding_tax_amount = Decimal("11")
    async_db_session.add_all(
        [
            portfolio_record(historical_event.portfolio_id),
            historical_record,
        ]
    )
    await async_db_session.commit()
    producer = MagicMock()
    repository = ReprocessingRepository(async_db_session, producer)

    with pytest.raises(ReprocessingReplayError) as exc_info:
        await repository.reprocess_transactions_by_ids([historical_event.transaction_id])

    assert exc_info.value.reason_code == TRANSACTION_REPLAY_SOURCE_INVALID
    assert exc_info.value.failed_transaction_ids == [historical_event.transaction_id]
    assert exc_info.value.published_record_count == 0
    assert str(exc_info.value) == (
        "Persisted transaction replay source is incompatible with the current transaction "
        "contract. No transaction was republished."
    )
    producer.publish_message.assert_not_called()
    producer.flush.assert_not_called()


async def _source_and_derived_effect_count(
    session: AsyncSession,
    transaction_id: str,
    portfolio_id: str,
) -> int:
    source_transaction_count = await session.scalar(
        select(func.count())
        .select_from(DBTransaction)
        .where(
            DBTransaction.transaction_id == transaction_id,
            DBTransaction.portfolio_id == portfolio_id,
        )
    )
    source_outbox_count = await session.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(
            OutboxEvent.aggregate_id == portfolio_id,
            OutboxEvent.event_type == "RawTransactionPersisted",
        )
    )
    cashflow_count = await session.scalar(
        select(func.count())
        .select_from(Cashflow)
        .where(
            Cashflow.transaction_id == transaction_id,
            Cashflow.portfolio_id == portfolio_id,
        )
    )
    position_count = await session.scalar(
        select(func.count())
        .select_from(PositionHistory)
        .where(
            PositionHistory.transaction_id == transaction_id,
            PositionHistory.portfolio_id == portfolio_id,
        )
    )
    generated_transaction_count = await session.scalar(
        select(func.count())
        .select_from(DBTransaction)
        .where(DBTransaction.originating_transaction_id == transaction_id)
    )
    processed_count = await session.scalar(
        select(func.count())
        .select_from(ProcessedEvent)
        .where(
            ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
            ProcessedEvent.tenant_id == TEST_TENANT_ID,
            ProcessedEvent.portfolio_id == portfolio_id,
            ProcessedEvent.semantic_key.contains(transaction_id),
        )
    )
    return sum(
        int(count or 0)
        for count in (
            source_transaction_count,
            source_outbox_count,
            cashflow_count,
            position_count,
            generated_transaction_count,
            processed_count,
        )
    )
