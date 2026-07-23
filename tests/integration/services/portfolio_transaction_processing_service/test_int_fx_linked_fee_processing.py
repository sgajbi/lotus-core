"""Prove separately linked FX fees retain economics and replay identity."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from portfolio_common.database_models import Cashflow
from portfolio_common.events import TransactionEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayStatus,
    ReplayBookedTransactionCommand,
    TransactionProcessingStatus,
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


async def test_fx_and_separate_linked_fee_replay_without_inline_netting_or_double_count(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-FX-LINKED-FEE-01"
    cash_security_id = "CASH_USD_FX_LINKED_FEE_01"
    fx_transaction_id = "FX-SPOT-BUY-LINKED-FEE-01"
    fee_transaction_id = "FEE-FX-SPOT-LINKED-FEE-01"
    economic_event_id = "EVT-FX-SPOT-LINKED-FEE-01"
    linked_group_id = "LTG-FX-SPOT-LINKED-FEE-01"
    correlation_id = "corr-fx-linked-fee-01"
    transaction_date = datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)
    fx_event = booked_transaction_event(
        transaction_id=fx_transaction_id,
        portfolio_id=portfolio_id,
        security_id=cash_security_id,
        transaction_date=transaction_date,
        transaction_type="FX_SPOT",
        quantity="0",
        price="0",
        gross_amount="110000",
        settlement_date=transaction_date,
        component_type="FX_CASH_SETTLEMENT_BUY",
        component_id="FX-SPOT-LINKED-FEE-01-BUY",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        calculation_policy_id="FX_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        fx_cash_leg_role="BUY",
        linked_fx_cash_leg_id="FX-SPOT-LINKED-FEE-01-SELL",
        settlement_status="SETTLED",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        fx_rate_quote_convention="QUOTE_PER_BASE",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("110000"),
        sell_amount=Decimal("100000"),
        contract_rate=Decimal("1.10"),
        spot_exposure_model="NONE",
        fx_realized_pnl_mode="NONE",
    )
    fee_event = booked_transaction_event(
        transaction_id=fee_transaction_id,
        portfolio_id=portfolio_id,
        security_id=cash_security_id,
        transaction_date=transaction_date,
        transaction_type="FEE",
        quantity="0",
        price="0",
        gross_amount="25",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                cash_security_id,
                name="US Dollar cash for linked FX fee proof",
                isin="CASHUSDFXLINKEDFEE01",
                currency="USD",
            ),
            canonical_transaction_record(fx_event),
            canonical_transaction_record(fee_event),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    producer = _CapturingReplayProducer()
    replay_use_case = build_replay_booked_transaction_use_case(
        session_factory=context.session_factory,
        kafka_producer=producer,
    )

    for transaction_id in (fx_transaction_id, fee_transaction_id):
        replay_result = await replay_use_case.execute(
            ReplayBookedTransactionCommand(
                transaction_id=transaction_id,
                correlation_id=correlation_id,
            )
        )
        assert replay_result.status is BookedTransactionReplayStatus.REPLAYED

    replay_events = [
        TransactionEvent.model_validate(message["value"]) for message in producer.messages
    ]
    assert {message["key"] for message in producer.messages} == {
        f"{portfolio_id}|transaction-group|{linked_group_id}"
    }
    assert {event.economic_event_id for event in replay_events} == {economic_event_id}
    assert {event.linked_transaction_group_id for event in replay_events} == {linked_group_id}
    assert replay_events[0].trade_fee == Decimal("0")
    assert replay_events[1].gross_transaction_amount == Decimal("25")

    first_results = []
    duplicate_results = []
    for sequence, event in enumerate(replay_events, start=1):
        first_results.append(
            await process_booked_transaction(
                context=context,
                event=event,
                event_id=f"transactions.persisted-0-94{sequence:02d}",
                correlation_id=correlation_id,
            )
        )
        duplicate_results.append(
            await process_booked_transaction(
                context=context,
                event=event,
                event_id=f"transactions.persisted-0-95{sequence:02d}",
                correlation_id=correlation_id,
            )
        )
    assert [result.status for result in first_results] == [
        TransactionProcessingStatus.PROCESSED,
        TransactionProcessingStatus.PROCESSED,
    ]
    assert [result.status for result in duplicate_results] == [
        TransactionProcessingStatus.DUPLICATE,
        TransactionProcessingStatus.DUPLICATE,
    ]

    async with context.session_factory() as verification_session:
        cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(Cashflow.linked_transaction_group_id == linked_group_id)
                    .order_by(Cashflow.transaction_id)
                )
            )
            .scalars()
            .all()
        )
    assert [
        (cashflow.transaction_id, cashflow.amount, cashflow.economic_event_id)
        for cashflow in cashflows
    ] == [
        (fee_transaction_id, Decimal("-25"), economic_event_id),
        (fx_transaction_id, Decimal("110000"), economic_event_id),
    ]
