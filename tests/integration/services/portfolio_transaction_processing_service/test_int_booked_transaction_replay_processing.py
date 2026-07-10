from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from portfolio_common.database_models import Cashflow, OutboxEvent, PositionHistory, ProcessedEvent
from portfolio_common.events import TransactionEvent
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayStatus,
    ReplayBookedTransactionCommand,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
    build_replay_booked_transaction_use_case,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
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


class CapturingReplayProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.flush_count = 0

    def publish_message(
        self,
        *,
        topic: str,
        key: str,
        value: dict[str, Any],
        headers: list[tuple[str, bytes]],
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "key": key,
                "value": value,
                "headers": headers,
            }
        )

    def flush(self) -> int:
        self.flush_count += 1
        return 0


async def test_duplicate_replay_requests_preserve_single_derived_transaction_state(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-REPLAY-01"
    transaction_id = "ADJ-COMBINED-REPLAY-01"
    correlation_id = "corr-combined-replay-01"
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id="CASH",
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="ADJUSTMENT",
        quantity="0",
        price="0",
        gross_amount="125.50",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            canonical_transaction_record(event),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    producer = CapturingReplayProducer()
    replay_use_case = build_replay_booked_transaction_use_case(
        session_factory=context.session_factory,
        kafka_producer=producer,
    )

    first_replay = await replay_use_case.execute(
        ReplayBookedTransactionCommand(
            transaction_id=transaction_id,
            correlation_id=correlation_id,
        )
    )
    second_replay = await replay_use_case.execute(
        ReplayBookedTransactionCommand(
            transaction_id=transaction_id,
            correlation_id=correlation_id,
        )
    )

    assert first_replay.status is BookedTransactionReplayStatus.REPLAYED
    assert second_replay.status is BookedTransactionReplayStatus.REPLAYED
    assert producer.flush_count == 2
    assert len(producer.messages) == 2
    assert all(message["topic"] == "transactions.persisted" for message in producer.messages)
    assert all(message["key"] == portfolio_id for message in producer.messages)
    assert all(
        message["headers"] == [("correlation_id", correlation_id.encode("utf-8"))]
        for message in producer.messages
    )
    replay_events = [
        TransactionEvent.model_validate(message["value"]) for message in producer.messages
    ]
    assert [replay_event.transaction_id for replay_event in replay_events] == [
        transaction_id,
        transaction_id,
    ]

    first_processing = await process_booked_transaction(
        context=context,
        event=replay_events[0],
        event_id="transactions.persisted-0-9101",
        correlation_id=correlation_id,
    )
    second_processing = await process_booked_transaction(
        context=context,
        event=replay_events[1],
        event_id="transactions.persisted-0-9102",
        correlation_id=correlation_id,
    )

    assert first_processing.status is TransactionProcessingStatus.PROCESSED
    assert second_processing.status is TransactionProcessingStatus.DUPLICATE
    assert first_processing.cashflow_record_count == 1
    assert second_processing.cashflow_record_count == 0
    assert first_processing.position_record_count == 1
    assert second_processing.position_record_count == 0

    async with context.session_factory() as verification_session:
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(Cashflow)
                .where(Cashflow.transaction_id == transaction_id),
            )
            == 1
        )
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(PositionHistory)
                .where(PositionHistory.transaction_id == transaction_id),
            )
            == 1
        )
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(ProcessedEvent)
                .where(
                    ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
                    ProcessedEvent.semantic_key
                    == (
                        "transaction-processing:v1:PORT-COMBINED-REPLAY-01:"
                        "ADJ-COMBINED-REPLAY-01:0"
                    ),
                    ProcessedEvent.payload_fingerprint.isnot(None),
                ),
            )
            == 1
        )
        compatibility_event_types = (
            (
                await verification_session.execute(
                    select(OutboxEvent.event_type)
                    .where(OutboxEvent.aggregate_id == portfolio_id)
                    .order_by(OutboxEvent.event_type, OutboxEvent.id)
                )
            )
            .scalars()
            .all()
        )

    assert compatibility_event_types == [
        "CashflowCalculated",
        "ProcessedTransactionPersisted",
    ]


async def _row_count(session: AsyncSession, statement) -> int:
    return int(await session.scalar(statement) or 0)
