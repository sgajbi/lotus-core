"""Prove fee-dominated settlement rejection across persistence and replay."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from portfolio_common.database_models import (
    Cashflow,
    OutboxEvent,
    PositionHistory,
    ProcessedEvent,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayStatus,
    ReplayBookedTransactionCommand,
    TransactionProcessingIntent,
    TransactionProcessingRejected,
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


class _CapturingReplayProducer:
    """Capture replay messages without an external broker dependency."""

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


def _fee_dominated_event(
    transaction_type: str,
    *,
    transaction_id: str,
    fee_amount: str,
) -> TransactionEvent:
    gross_amount = "10" if transaction_type == "INTEREST" else "100"
    domain_fields: dict[str, object] = {
        "settlement_date": datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
    }
    if transaction_type == "INTEREST":
        domain_fields.update(
            {
                "withholding_tax_amount": Decimal("2"),
                "net_interest_amount": Decimal("8"),
                "interest_direction": "INCOME",
            }
        )
    return booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id="PORT-FEE-DOMINATED-01",
        security_id="SEC-FEE-DOMINATED-01",
        transaction_date=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity="1" if transaction_type == "SELL" else "0",
        price="100" if transaction_type == "SELL" else "0",
        gross_amount=gross_amount,
        trade_fee=fee_amount,
        **domain_fields,
    )


@pytest.mark.parametrize(
    ("transaction_type", "fee_amount", "reason_code"),
    [
        ("SELL", "100", "SELL_010_NON_POSITIVE_NET_SETTLEMENT"),
        ("SELL", "100.01", "SELL_010_NON_POSITIVE_NET_SETTLEMENT"),
        ("DIVIDEND", "100", "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"),
        ("DIVIDEND", "100.01", "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"),
        ("INTEREST", "8", "INTEREST_017_NON_POSITIVE_NET_SETTLEMENT"),
        ("INTEREST", "8.01", "INTEREST_017_NON_POSITIVE_NET_SETTLEMENT"),
    ],
)
async def test_fee_dominated_settlement_leaves_no_derived_state(
    clean_db,
    async_db_session: AsyncSession,
    transaction_type: str,
    fee_amount: str,
    reason_code: str,
) -> None:
    transaction_id = f"{transaction_type}-FEE-DOMINATED-{fee_amount.replace('.', '-')}"
    event = _fee_dominated_event(
        transaction_type,
        transaction_id=transaction_id,
        fee_amount=fee_amount,
    )
    async_db_session.add_all(
        [
            portfolio_record(event.portfolio_id),
            canonical_transaction_record(event),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    with pytest.raises(TransactionProcessingRejected) as raised:
        await process_booked_transaction(
            context=context,
            event=event,
            event_id=f"transactions.persisted-0-{transaction_id}",
            correlation_id=f"corr-{transaction_id}",
        )

    assert raised.value.reason_code == reason_code
    assert raised.value.retryable is False
    assert raised.value.detail["fee_amount"] == fee_amount
    assert await _source_transaction_count(context.session_factory, transaction_id) == 1
    assert await _derived_state_count(context.session_factory, transaction_id) == 0


async def test_replay_repeats_settlement_rejection_without_claiming_idempotency(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    transaction_id = "DIVIDEND-FEE-DOMINATED-REPLAY-01"
    event = _fee_dominated_event(
        "DIVIDEND",
        transaction_id=transaction_id,
        fee_amount="101",
    )
    async_db_session.add_all(
        [
            portfolio_record(event.portfolio_id),
            canonical_transaction_record(event),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    producer = _CapturingReplayProducer()
    replay_use_case = build_replay_booked_transaction_use_case(
        session_factory=context.session_factory,
        kafka_producer=producer,
    )

    for sequence in (1, 2):
        replay_result = await replay_use_case.execute(
            ReplayBookedTransactionCommand(
                transaction_id=transaction_id,
                correlation_id=f"corr-fee-dominated-replay-{sequence}",
            )
        )
        replay_event = TransactionEvent.model_validate(producer.messages[-1]["value"])

        assert replay_result.status is BookedTransactionReplayStatus.REPLAYED
        with pytest.raises(TransactionProcessingRejected) as raised:
            await process_booked_transaction(
                context=context,
                event=replay_event,
                event_id=f"transactions.persisted-0-replay-{sequence}",
                correlation_id=f"corr-fee-dominated-replay-{sequence}",
                processing_intent=TransactionProcessingIntent.REPAIR,
            )
        assert raised.value.reason_code == "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"

    assert await _derived_state_count(context.session_factory, transaction_id) == 0


async def _source_transaction_count(session_factory, transaction_id: str) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(DBTransaction)
                .where(DBTransaction.transaction_id == transaction_id)
            )
            or 0
        )


async def _derived_state_count(session_factory, transaction_id: str) -> int:
    async with session_factory() as session:
        counts = [
            await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.transaction_id == transaction_id)
            )
            for model in (Cashflow, PositionHistory, TransactionCost)
        ]
        processed_count = await session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(
                ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
                ProcessedEvent.semantic_key.contains(transaction_id),
            )
        )
        outbox_count = await session.scalar(select(func.count()).select_from(OutboxEvent))
        return sum(int(count or 0) for count in [*counts, processed_count, outbox_count])
