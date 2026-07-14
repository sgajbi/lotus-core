from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from portfolio_common.database_models import Cashflow, OutboxEvent, PositionHistory, ProcessedEvent
from portfolio_common.events import TransactionEvent
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayStatus,
    ReplayBookedTransactionCommand,
    TransactionProcessingIntent,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    SqlAlchemyCashflowRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.idempotency import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
)
from src.services.portfolio_transaction_processing_service.app.runtime.dependency_composition import (  # noqa: E501
    build_replay_booked_transaction_use_case,
)
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
        message["headers"]
        == [
            ("correlation_id", correlation_id.encode("utf-8")),
            ("lotus-transaction-processing-intent", b"repair"),
        ]
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
                        "transaction-processing:v1:PORT-COMBINED-REPLAY-01:ADJ-COMBINED-REPLAY-01:0"
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


async def test_replay_after_processing_repairs_missing_derived_state(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-REPLAY-02"
    transaction_id = "BUY-COMBINED-REPLAY-02"
    correlation_id = "corr-combined-replay-02"
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id="SEC-COMBINED-REPLAY-02",
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="25",
        gross_amount="250",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-REPLAY-02",
        settlement_cash_instrument_id="CASH-USD-REPLAY-02",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                "SEC-COMBINED-REPLAY-02",
                name="Combined replay security",
                isin="SG0000000002",
                currency="USD",
            ),
            canonical_transaction_record(event),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    first_processing = await process_booked_transaction(
        context=context,
        event=event,
        event_id="transactions.persisted-0-9201",
        correlation_id=correlation_id,
    )
    await async_db_session.execute(delete(Cashflow).where(Cashflow.portfolio_id == portfolio_id))
    await async_db_session.execute(
        delete(PositionHistory).where(PositionHistory.portfolio_id == portfolio_id)
    )
    await async_db_session.commit()

    producer = CapturingReplayProducer()
    replay_use_case = build_replay_booked_transaction_use_case(
        session_factory=context.session_factory,
        kafka_producer=producer,
    )
    replay_result = await replay_use_case.execute(
        ReplayBookedTransactionCommand(
            transaction_id=transaction_id,
            correlation_id=correlation_id,
        )
    )
    replay_event = TransactionEvent.model_validate(producer.messages[0]["value"])
    repair_processing = await process_booked_transaction(
        context=context,
        event=replay_event,
        event_id="transactions.persisted-0-9202",
        correlation_id=correlation_id,
        processing_intent=TransactionProcessingIntent.REPAIR,
    )

    assert first_processing.status is TransactionProcessingStatus.PROCESSED
    assert replay_result.status is BookedTransactionReplayStatus.REPLAYED
    assert replay_event.net_cost is not None
    assert replay_event.calculation_policy_id == "BUY_DEFAULT_POLICY"
    assert replay_event.external_cash_transaction_id == f"{transaction_id}-CASHLEG"
    assert repair_processing.status is TransactionProcessingStatus.PROCESSED
    assert repair_processing.cashflow_record_count > 0
    assert repair_processing.position_record_count > 0

    async with context.session_factory() as verification_session:
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(Cashflow)
                .where(Cashflow.portfolio_id == portfolio_id),
            )
            > 0
        )
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(PositionHistory)
                .where(PositionHistory.portfolio_id == portfolio_id),
            )
            > 0
        )


async def test_replay_after_processing_replaces_corrupted_cashflow_state(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-REPLAY-03"
    transaction_id = "ADJ-COMBINED-REPLAY-03"
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
    async_db_session.add_all([portfolio_record(portfolio_id), canonical_transaction_record(event)])
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    await process_booked_transaction(
        context=context,
        event=event,
        event_id="transactions.persisted-0-9301",
        correlation_id="corr-combined-replay-03",
    )
    original_amount = await async_db_session.scalar(
        select(Cashflow.amount).where(Cashflow.transaction_id == transaction_id)
    )
    await async_db_session.execute(
        update(Cashflow).where(Cashflow.transaction_id == transaction_id).values(amount="999999")
    )
    await async_db_session.commit()

    repair_result = await process_booked_transaction(
        context=context,
        event=event,
        event_id="transactions.persisted-0-9302",
        correlation_id="corr-combined-replay-03",
        processing_intent=TransactionProcessingIntent.REPAIR,
    )

    assert repair_result.status is TransactionProcessingStatus.PROCESSED
    assert repair_result.cashflow_record_count == 1
    async with context.session_factory() as verification_session:
        repaired_amount = await verification_session.scalar(
            select(Cashflow.amount).where(Cashflow.transaction_id == transaction_id)
        )
    assert repaired_amount == original_amount


async def test_concurrent_missing_cashflow_repairs_converge_on_one_row(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-REPLAY-04"
    transaction_id = "ADJ-COMBINED-REPLAY-04"
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
    async_db_session.add_all([portfolio_record(portfolio_id), canonical_transaction_record(event)])
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    async def repair(amount: Decimal) -> int:
        async with context.session_factory() as session, session.begin():
            repository = SqlAlchemyCashflowRepository(session)
            stored = await repository.replace(
                Cashflow(
                    transaction_id=transaction_id,
                    portfolio_id=portfolio_id,
                    security_id="CASH",
                    cashflow_date=event.transaction_date.date(),
                    epoch=0,
                    amount=amount,
                    currency="USD",
                    classification="TRANSFER",
                    timing="EOD",
                    calculation_type="NET",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                )
            )
            return stored.cashflow_id

    stored_ids = await asyncio.gather(
        repair(Decimal("125.50")),
        repair(Decimal("125.50")),
    )

    assert stored_ids[0] == stored_ids[1]
    async with context.session_factory() as verification_session:
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(Cashflow)
                .where(
                    Cashflow.transaction_id == transaction_id,
                    Cashflow.epoch == 0,
                ),
            )
            == 1
        )


async def test_replay_after_processing_ignores_processor_owned_transaction_outputs(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-REPLAY-05"
    transaction_id = "BUY-COMBINED-REPLAY-05"
    correlation_id = "corr-combined-replay-05"
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id="SEC-COMBINED-REPLAY-05",
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="25",
        gross_amount="250",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                "SEC-COMBINED-REPLAY-05",
                name="Combined replay identity security",
                isin="SG0000000005",
                currency="USD",
            ),
            canonical_transaction_record(event),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    first_processing = await process_booked_transaction(
        context=context,
        event=event,
        event_id="transactions.persisted-0-9501",
        correlation_id=correlation_id,
    )
    producer = CapturingReplayProducer()
    replay_use_case = build_replay_booked_transaction_use_case(
        session_factory=context.session_factory,
        kafka_producer=producer,
    )
    replay_result = await replay_use_case.execute(
        ReplayBookedTransactionCommand(
            transaction_id=transaction_id,
            correlation_id=correlation_id,
        )
    )
    replay_event = TransactionEvent.model_validate(producer.messages[0]["value"])
    duplicate_processing = await process_booked_transaction(
        context=context,
        event=replay_event,
        event_id="transactions.persisted-0-9502",
        correlation_id=correlation_id,
    )

    assert first_processing.status is TransactionProcessingStatus.PROCESSED
    assert replay_result.status is BookedTransactionReplayStatus.REPLAYED
    assert replay_event.net_cost is not None
    assert replay_event.calculation_policy_id == "BUY_DEFAULT_POLICY"
    assert duplicate_processing.status is TransactionProcessingStatus.DUPLICATE


async def _row_count(session: AsyncSession, statement) -> int:
    return int(await session.scalar(statement) or 0)
