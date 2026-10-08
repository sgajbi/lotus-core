from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any

import pytest
from portfolio_common.database_models import Cashflow, OutboxEvent, PositionHistory, ProcessedEvent
from portfolio_common.domain.calculation_lineage import (
    calculation_lineage_from_payload,
    canonical_content_hash,
)
from portfolio_common.domain.transaction.fee_components import TRANSACTION_FEE_COMPONENT_FIELDS
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
)
from portfolio_common.events import TransactionEvent
from portfolio_common.reprocessing_replay import (
    TRANSACTION_REPLAY_SOURCE_INVALID,
    ReprocessingReplayError,
)
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayStatus,
    ReplayBookedTransactionCommand,
    TransactionProcessingIntent,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    build_transaction_semantic_identity,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    SqlAlchemyCashflowRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    transaction_repository as fee_cost_repository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.processing_state_repository import (  # noqa: E501
    SqlAlchemyCostBasisProcessingStateRepository,
    cost_basis_processing_lock_key,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.idempotency import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping.booked_transaction import (  # noqa: E501
    to_booked_transaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_processing import (  # noqa: E501
    SqlAlchemyTransactionProcessingUnitOfWork,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay.booked_transaction import (  # noqa: E501
    SqlAlchemyQualifiedTransactionReplayReader,
)
from src.services.portfolio_transaction_processing_service.app.runtime.dependency_composition import (  # noqa: E501
    build_replay_booked_transaction_use_case,
)
from tests.test_support.async_task_coordination import wait_for_task_signal
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    cash_account_record,
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
    assert all(message["key"] == f"{portfolio_id}|CASH" for message in producer.messages)
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
    async_db_session.add(portfolio_record(portfolio_id))
    await async_db_session.flush()
    async_db_session.add_all(
        [
            instrument_record(
                "SEC-COMBINED-REPLAY-02",
                name="Combined replay security",
                isin="SG0000000002",
                currency="USD",
            ),
            instrument_record(
                "CASH-USD-REPLAY-02",
                name="Replay USD settlement cash",
                isin="CASHUSDRP002",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            cash_account_record(
                "CASH-USD-REPLAY-02",
                portfolio_id=portfolio_id,
                security_id="CASH-USD-REPLAY-02",
                account_currency="USD",
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


@pytest.mark.parametrize("shape", ["absent", "explicit-zero", "sparse", "aggregate-only"])
@pytest.mark.parametrize("later_damage", [None, "fee", "malformed"])
async def test_persisted_raw_fee_authority_preserves_presence_and_refuses_later_bad_rows(
    clean_db,
    async_db_session: AsyncSession,
    shape: str,
    later_damage: str | None,
) -> None:
    portfolio_id = "PORT-RAW-FEE-AUTHORITY"
    fields = {
        "absent": {},
        "explicit-zero": {"brokerage": Decimal(0), "gst": Decimal(0)},
        "sparse": {"brokerage": Decimal("1.25"), "gst": Decimal(0)},
        "aggregate-only": {},
    }[shape]
    event = booked_transaction_event(
        transaction_id="BUY-RAW-FEE-AUTHORITY",
        portfolio_id=portfolio_id,
        security_id="SEC-RAW-FEE-AUTHORITY",
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="25",
        gross_amount="250",
        trade_fee="1.25" if shape in {"sparse", "aggregate-only"} else "0",
        **fields,
    )
    canonical = canonical_transaction_record(event)
    original_fingerprint = canonical.payload_fingerprint
    raw_payload = event.model_dump(mode="json")
    later_payload = dict(raw_payload)
    if later_damage == "fee":
        later_payload["brokerage"] = "99"
    elif later_damage == "malformed":
        later_payload["gross_transaction_amount"] = "not-a-number"
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                "SEC-RAW-FEE-AUTHORITY",
                name="Raw fee authority equity",
                isin="SG0000000795",
                currency="USD",
            ),
            canonical,
            *[
                OutboxEvent(
                    aggregate_type="RawTransaction",
                    aggregate_id=portfolio_id,
                    event_type="RawTransactionPersisted",
                    topic="raw_transactions",
                    payload=payload,
                    status="PROCESSED",
                )
                for payload in (raw_payload, later_payload)
            ],
        ]
    )
    await async_db_session.commit()
    reader = SqlAlchemyQualifiedTransactionReplayReader(async_db_session)

    if later_damage is not None:
        with pytest.raises(ReprocessingReplayError) as refused:
            await reader.list_transactions_to_replay([event.transaction_id])
        assert isinstance(refused.value.__cause__, ValueError)
    else:
        rows = await reader.list_transactions_to_replay([event.transaction_id])
        assert len(rows) == 1
        assert {name: getattr(rows[0], name) for name in TRANSACTION_FEE_COMPONENT_FIELDS} | {
            "trade_fee": rows[0].trade_fee
        } == {name: getattr(event, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS} | {
            "trade_fee": event.trade_fee
        }
    await async_db_session.refresh(canonical)
    assert canonical.payload_fingerprint == original_fingerprint
    assert canonical.trade_fee == event.trade_fee
    assert (
        await _row_count(
            async_db_session,
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.event_type == "RawTransactionPersisted",
                OutboxEvent.aggregate_id == portfolio_id,
            ),
        )
        == 2
    )
    assert (
        await _row_count(
            async_db_session,
            select(func.count())
            .select_from(ProcessedEvent)
            .where(ProcessedEvent.portfolio_id == portfolio_id),
        )
        == 0
    )
    assert (
        await _row_count(
            async_db_session,
            select(func.count()).select_from(Cashflow).where(Cashflow.portfolio_id == portfolio_id),
        )
        == 0
    )


async def _row_count(session: AsyncSession, statement) -> int:
    return int(await session.scalar(statement) or 0)


# Full rows in these explicit affected tables, not count-only rollback proof. The
# future db_direct fixture must be independently owned; this is read-only and
# stronger than portfolio filtering for shared allocation/receipt tables.
_CORE795_ROLLBACK_TABLES = (
    "transactions",
    "transaction_costs",
    "cashflows",
    "position_history",
    "position_state",
    "position_lot_state",
    "average_cost_pool_state",
    "cost_basis_processing_state",
    "lot_disposal_receipts",
    "lot_disposal_allocations",
    "lot_basis_transfer_receipts",
    "lot_basis_transfer_allocations",
    "lot_amortized_cost_authority",
    "lot_amortized_cost_profiles",
    "lot_amortized_cost_periods",
    "accrued_income_offset_state",
    "processed_events",
    "transaction_source_revisions",
    "pipeline_stage_state",
    "outbox_events",
    "portfolio_cashflow_source_cuts",
    "portfolio_cashflow_source_cut_refresh_queue",
)


async def _core795_snapshot(session):
    snapshot = {}
    for table in _CORE795_ROLLBACK_TABLES:
        # Names are the literal allowlist above, never caller-controlled identifiers.
        snapshot[table] = tuple(
            (
                await session.execute(
                    text(f'SELECT to_jsonb(t)::text FROM "{table}" t ORDER BY to_jsonb(t)::text')
                )
            )
            .scalars()
            .all()
        )
    return snapshot


async def _core795_backend(session):
    return dict(
        (
            await session.execute(
                text(
                    "SELECT pid, backend_start, datid, datname FROM pg_stat_activity "
                    "WHERE pid=pg_backend_pid()"
                )
            )
        )
        .mappings()
        .one()
    )


async def _core795_seed(session, portfolio, *, later_bad=None):
    security = f"SEC-{portfolio}"
    events = [
        booked_transaction_event(
            transaction_id=f"BUY-{portfolio}-{index}",
            portfolio_id=portfolio,
            # Both canonical sources are precommitted. The earlier waiter rebuilds
            # their dated history/lots; delivery receipts/cashflows remain separate.
            security_id=security,
            transaction_date=datetime(2026, 1, 6 - index, 10, tzinfo=timezone.utc),
            transaction_type="BUY",
            quantity="10",
            price="25",
            gross_amount="250",
            trade_fee="3",
            brokerage=Decimal(1),
            stamp_duty=Decimal(0),
            exchange_fee=Decimal(2),
            gst=None,
            other_fees=Decimal(0),
        )
        for index in range(2 if not later_bad else 1)
    ]
    session.add_all(
        [
            portfolio_record(portfolio),
            instrument_record(
                security,
                name="Core795 fee authority rollback",
                isin="SG0000000795",
                currency="USD",
            ),
        ]
    )
    for event in events:
        session.add(canonical_transaction_record(event))
        payloads = [event.model_dump(mode="json")]
        if later_bad:
            payloads.append(
                payloads[0]
                | (
                    {"brokerage": "99"}
                    if later_bad == "fee"
                    else {"gross_transaction_amount": "not-a-number"}
                )
            )
        session.add_all(
            [
                OutboxEvent(
                    aggregate_type="RawTransaction",
                    aggregate_id=portfolio,
                    event_type="RawTransactionPersisted",
                    topic="raw_transactions",
                    payload=payload,
                    status="PROCESSED",
                )
                for payload in payloads
            ]
        )
    await session.commit()  # Precommitted ingress is explicitly part of baseline.
    return events


async def _core795_wait_for_same_key_block(task, factory, holder, waiter, key):
    deadline = asyncio.get_running_loop().time() + 10
    while asyncio.get_running_loop().time() < deadline:
        if task.done():
            task.result()
            raise AssertionError("waiter completed without the expected real lock wait")
        async with factory() as observer:
            rows = (
                (
                    await observer.execute(
                        text(
                            "SELECT a.pid,a.backend_start,a.datid,a.datname,l.classid,l.objid,"
                            "l.objsubid,l.granted,pg_blocking_pids(a.pid) blockers "
                            "FROM pg_stat_activity a JOIN pg_locks l ON l.pid=a.pid "
                            "WHERE a.pid IN (:holder,:waiter) AND l.locktype='advisory' "
                            "AND l.classid=:high AND l.objid=:low AND l.objsubid=1"
                        ),
                        {
                            "holder": holder["pid"],
                            "waiter": waiter["pid"],
                            "high": (key & ((1 << 64) - 1)) >> 32,
                            "low": key & 0xFFFFFFFF,
                        },
                    )
                )
                .mappings()
                .all()
            )
        granted = [row for row in rows if row["pid"] == holder["pid"] and row["granted"]]
        blocked = [row for row in rows if row["pid"] == waiter["pid"] and not row["granted"]]
        if granted and blocked:
            for row, identity in [(granted[0], holder), (blocked[0], waiter)]:
                assert (row["backend_start"], row["datid"], row["datname"]) == (
                    identity["backend_start"],
                    identity["datid"],
                    identity["datname"],
                )
            assert holder["pid"] in blocked[0]["blockers"]
            return [dict(row) for row in rows]
        await asyncio.sleep(0.01)
    raise AssertionError("no birth/database-qualified same-key PostgreSQL blocker observed")


async def _core795_assert_financial_once(factory, events, *, source_cohort):
    async with factory() as session:
        for event in events:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT net_cost,trade_fee FROM transactions WHERE transaction_id=:id"
                        ),
                        {"id": event.transaction_id},
                    )
                )
                .mappings()
                .one()
            )
            assert row["net_cost"] == Decimal(253)
            assert row["trade_fee"] == Decimal(3)
            costs = (
                await session.execute(
                    text(
                        (
                            "SELECT fee_type,amount FROM transaction_costs WHER"
                            "E transaction_id=:id ORDER BY fee_type"
                        )
                    ),
                    {"id": event.transaction_id},
                )
            ).all()
            assert costs == [("brokerage", Decimal(1)), ("exchange_fee", Decimal(2))]
            raw = (
                (
                    await session.execute(
                        text(
                            """
SELECT payload FROM outbox_events WHERE
event_type='RawTransactionPersisted' AND
payload->>'transaction_id'=:id
"""
                        ),
                        {"id": event.transaction_id},
                    )
                )
                .scalars()
                .one()
            )
            original = TransactionEvent.model_validate(raw)
            assert {
                field: getattr(original, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS
            } == {
                "brokerage": Decimal(1),
                "stamp_duty": Decimal(0),
                "exchange_fee": Decimal(2),
                "gst": None,
                "other_fees": Decimal(0),
            }
            identity = build_transaction_semantic_identity(to_booked_transaction(event))
            receipt = (
                (
                    await session.execute(
                        text(
                            """
SELECT payload_fingerprint FROM processed_events WHERE
portfolio_id=:portfolio AND service_name=:service AND
tenant_id=:tenant AND semantic_key=:key
"""
                        ),
                        {
                            "portfolio": event.portfolio_id,
                            "tenant": event.tenant_id,
                            "service": TRANSACTION_PROCESSING_SERVICE_NAME,
                            "key": identity.semantic_key,
                        },
                    )
                )
                .scalars()
                .one()
            )
            assert receipt == identity.payload_fingerprint
            flow = (
                await session.execute(
                    text(
                        (
                            "SELECT classification,amount,currency FROM cashflo"
                            "ws WHERE transaction_id=:id AND epoch=0"
                        )
                    ),
                    {"id": event.transaction_id},
                )
            ).all()
            assert flow == [("INVESTMENT_OUTFLOW", Decimal(-253), "USD")]
            lot = (
                await session.execute(
                    text(
                        "SELECT original_quantity,open_quantity,lot_cost_local,lot_cost_base "
                        "FROM position_lot_state WHERE source_transaction_id=:id"
                    ),
                    {"id": event.transaction_id},
                )
            ).one()
            assert tuple(lot) == (Decimal(10), Decimal(10), Decimal(253), Decimal(253))
            stage = (
                await session.execute(
                    text(
                        """
SELECT
stage_name,status,cost_event_seen,cashflow_event_seen,epoch,security_id,business_date
FROM pipeline_stage_state WHERE transaction_id=:id AND
stage_name='TRANSACTION_PROCESSING'
"""
                    ),
                    {"id": event.transaction_id},
                )
            ).one()
            assert tuple(stage) == (
                "TRANSACTION_PROCESSING",
                "COMPLETED",
                True,
                True,
                0,
                event.security_id,
                event.transaction_date.date(),
            )
            for kind in [
                "ProcessedTransactionPersisted",
                "CashflowCalculated",
                "TransactionProcessingCompleted",
            ]:
                payload = (
                    (
                        await session.execute(
                            text(
                                "SELECT payload FROM outbox_events WHERE event_type=:kind "
                                "AND payload->>'transaction_id'=:id"
                            ),
                            {"kind": kind, "id": event.transaction_id},
                        )
                    )
                    .scalars()
                    .one()
                )
                assert payload["portfolio_id"] == event.portfolio_id
                if kind == "ProcessedTransactionPersisted":
                    processed = TransactionEvent.model_validate(payload)
                    assert {
                        field: getattr(processed, field)
                        for field in TRANSACTION_FEE_COMPONENT_FIELDS
                    } == {
                        "brokerage": Decimal(1),
                        "stamp_duty": Decimal(0),
                        "exchange_fee": Decimal(2),
                        "gst": None,
                        "other_fees": Decimal(0),
                    }
                    assert processed.trade_fee == Decimal(3) and processed.net_cost == Decimal(253)
                elif kind == "CashflowCalculated":
                    assert Decimal(payload["amount"]) == Decimal(-253)
                else:
                    assert (
                        payload["epoch"] == 0
                        and payload["cost_event_seen"]
                        and payload["cashflow_event_seen"]
                    )
            assert (
                (
                    await session.execute(
                        text(
                            """
SELECT payload FROM outbox_events WHERE
event_type='PortfolioDayReadyForValuation' AND
payload->>'portfolio_id'=:portfolio AND
payload->>'security_id'=:security AND payload->>'valuation_date'=:day
AND payload->>'epoch'='0'
"""
                        ),
                        {
                            "portfolio": event.portfolio_id,
                            "security": event.security_id,
                            "day": event.transaction_date.date().isoformat(),
                        },
                    )
                )
                .scalars()
                .one()
            )
        positions = (
            await session.execute(
                text(
                    """
SELECT position_date,quantity,cost_basis,cost_basis_local FROM position_history
WHERE portfolio_id=:portfolio AND security_id=:security AND epoch=0
ORDER BY position_date
"""
                ),
                {"portfolio": events[0].portfolio_id, "security": events[0].security_id},
            )
        ).all()
        assert positions == [
            (
                event.transaction_date.date(),
                Decimal(10 * index),
                Decimal(253 * index),
                Decimal(253 * index),
            )
            for index, event in enumerate(
                sorted(source_cohort, key=lambda event: event.transaction_date), start=1
            )
        ]
        cohort_lots = (
            await session.execute(
                text(
                    "SELECT source_transaction_id,lot_id,acquisition_date,original_quantity,"
                    "open_quantity,lot_cost_local,lot_cost_base,calculation_lineage "
                    "FROM position_lot_state WHERE portfolio_id=:portfolio "
                    "AND security_id=:security ORDER BY source_transaction_id"
                ),
                {"portfolio": events[0].portfolio_id, "security": events[0].security_id},
            )
        ).all()
        assert len(cohort_lots) == len(source_cohort)
        for lot, source in zip(
            cohort_lots, sorted(source_cohort, key=lambda event: event.transaction_id), strict=True
        ):
            assert tuple(lot[:7]) == (
                source.transaction_id,
                f"LOT-{source.transaction_id}",
                source.transaction_date.date(),
                Decimal(10),
                Decimal(10),
                Decimal(253),
                Decimal(253),
            )
            _core795_assert_lineage(
                lot.calculation_lineage,
                "cost-basis-complete-lot-snapshot",
                1,
                COST_BASIS_STATE_LEDGER_OUTPUT_V1,
            )
        totals = (
            await session.execute(
                text(
                    """
SELECT sum(open_quantity),sum(lot_cost_local),sum(lot_cost_base) FROM
position_lot_state WHERE portfolio_id=:portfolio AND
security_id=:security
"""
                ),
                {"portfolio": events[0].portfolio_id, "security": events[0].security_id},
            )
        ).one()
        assert tuple(totals) == (
            Decimal(10 * len(source_cohort)),
            Decimal(253 * len(source_cohort)),
            Decimal(253 * len(source_cohort)),
        )
        cut = (
            (
                await session.execute(
                    text(
                        """
SELECT
cashflow_revision_count,cashflow_revision_digest,settlement_revision_count,settlement_revision_digest
FROM portfolio_cashflow_source_cuts WHERE portfolio_id=:portfolio
"""
                    ),
                    {"portfolio": events[0].portfolio_id},
                )
            )
            .mappings()
            .one()
        )
        # Governed cut selects latest cashflow per transaction and settlement-only
        # DEPOSIT/WITHDRAWAL; these BUYs must contribute ZERO settlement revisions.
        row_digests = (
            (
                await session.execute(
                    text(
                        """
SELECT
encode(sha256(convert_to(jsonb_build_array(transaction_id,epoch,cashflow_date,amount,currency,classification,timing,is_position_flow,is_portfolio_flow)::text,'UTF8')),'hex')
FROM cashflows WHERE portfolio_id=:portfolio ORDER BY transaction_id
COLLATE "C",epoch,id
"""
                    ),
                    {"portfolio": events[0].portfolio_id},
                )
            )
            .scalars()
            .all()
        )
        assert len(row_digests) == len(events)
        assert dict(cut) == {
            "cashflow_revision_count": len(events),
            "cashflow_revision_digest": sha256("".join(row_digests).encode()).hexdigest(),
            "settlement_revision_count": 0,
            "settlement_revision_digest": sha256(b"").hexdigest(),
        }
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM portfolio_cashflow_source_cut_refresh_queue "
                    "WHERE portfolio_id=:portfolio"
                ),
                {"portfolio": events[0].portfolio_id},
            )
            == 0
        )


def _core795_assert_lineage(payload, algorithm, version, policy):
    lineage = calculation_lineage_from_payload(payload)
    assert lineage is not None
    assert lineage.algorithm_id == algorithm and lineage.algorithm_version == version
    assert lineage.numeric_output_policy == policy.lineage_identity()
    assert lineage.intermediate_precision == policy.working_precision
    assert lineage.calculation_content_hash == canonical_content_hash(
        {
            "algorithm_id": algorithm,
            "algorithm_version": version,
            "input_content_hash": lineage.input_content_hash,
            "intermediate_precision": policy.working_precision,
            "numeric_output_policy": policy.lineage_identity().lineage_payload(),
        }
    )


async def _core795_assert_cancelled_delivery_absent(factory, event, baseline):
    identity = build_transaction_semantic_identity(to_booked_transaction(event))
    async with factory() as session:
        observations = {}
        for name, table, statement, parameters in [
            (
                "receipt",
                "processed_events",
                "SELECT count(*) FROM processed_events WHERE portfolio_id=:portfolio "
                "AND tenant_id=:tenant AND service_name=:service AND semantic_key=:key",
                {
                    "portfolio": event.portfolio_id,
                    "tenant": event.tenant_id,
                    "service": TRANSACTION_PROCESSING_SERVICE_NAME,
                    "key": identity.semantic_key,
                },
            ),
            (
                "cashflow",
                "cashflows",
                "SELECT count(*) FROM cashflows WHERE transaction_id=:id",
                {"id": event.transaction_id},
            ),
            (
                "stage",
                "pipeline_stage_state",
                "SELECT count(*) FROM pipeline_stage_state WHERE transaction_id=:id",
                {"id": event.transaction_id},
            ),
            (
                "processing_outbox",
                "outbox_events",
                "SELECT count(*) FROM outbox_events WHERE payload->>'transaction_id'=:id "
                "AND event_type IN ('ProcessedTransactionPersisted','CashflowCalculated',"
                "'TransactionProcessingCompleted')",
                {"id": event.transaction_id},
            ),
        ]:
            count = await session.scalar(text(statement), parameters)
            row_statement = statement.replace("SELECT count(*)", f"SELECT to_jsonb({table})::text")
            rows = (await session.execute(text(row_statement), parameters)).scalars().all()
            observations[name] = {
                "count": count,
                "rows": [json.loads(row, parse_float=Decimal) for row in rows],
                "parameters": parameters,
            }
        current = await _core795_snapshot(session)

        # Original ingress is not removed to manufacture successful rollback/recovery.
        def holder_ingress(snapshot):
            return tuple(
                row
                for row in snapshot["transactions"]
                if json.loads(row)["transaction_id"] == event.transaction_id
            )

        def raw_ingress(snapshot):
            return tuple(
                row
                for row in snapshot["outbox_events"]
                if json.loads(row)["event_type"] == "RawTransactionPersisted"
            )

        for name, observation in observations.items():
            assert observation["count"] == 0, (name, observation)
        assert len(holder_ingress(baseline)) == 1
        assert len(holder_ingress(current)) == 1
        before = json.loads(holder_ingress(baseline)[0], parse_float=Decimal)
        after = json.loads(holder_ingress(current)[0], parse_float=Decimal)
        # Waiter commit recomputes both canonical sources, not holder delivery.
        derived = {
            "calculation_lineage",
            "gross_cost",
            "net_cost",
            "net_cost_local",
            "realized_gain_loss",
            "realized_gain_loss_local",
            "transaction_fx_rate",
            "transaction_fx_rate_origin",
            "updated_at",
        }
        assert {key: value for key, value in after.items() if key not in derived} == {
            key: value for key, value in before.items() if key not in derived
        }
        assert {key: after[key] for key in derived - {"calculation_lineage", "updated_at"}} == {
            "gross_cost": Decimal(250),
            "net_cost": Decimal(253),
            "net_cost_local": Decimal(253),
            "realized_gain_loss": Decimal(0),
            "realized_gain_loss_local": Decimal(0),
            "transaction_fx_rate": Decimal(1),
            "transaction_fx_rate_origin": "REFERENCE_DERIVED",
        }
        _core795_assert_lineage(
            after["calculation_lineage"],
            "transaction-cost-basis-calculation",
            2,
            TRANSACTION_COST_LEDGER_OUTPUT_V1,
        )
        assert (
            datetime.fromisoformat(before["updated_at"])
            < datetime.fromisoformat(after["updated_at"])
            <= datetime.now(timezone.utc)
        )
        assert len(raw_ingress(baseline)) == 2
        assert raw_ingress(current) == raw_ingress(baseline)
        raw_event = TransactionEvent.model_validate(
            next(
                json.loads(row, parse_float=Decimal)["payload"]
                for row in raw_ingress(current)
                if json.loads(row)["payload"]["transaction_id"] == event.transaction_id
            )
        )
        assert tuple(getattr(raw_event, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS) == (
            Decimal(1),
            Decimal(0),
            Decimal(2),
            None,
            Decimal(0),
        )


async def test_cancelled_fee_qualified_combined_uow_rolls_back_and_releases_same_key_lock(
    clean_db,
    async_db_session,
    monkeypatch,
):
    events = await _core795_seed(async_db_session, "PORT-CORE795-CANCEL")
    context = transaction_processing_test_context(async_db_session)
    async with context.session_factory() as observer:
        baseline = await _core795_snapshot(observer)
    holder_ready, waiter_ready, waiter_lock_attempt = (asyncio.Event() for _ in range(3))
    release_holder, release_waiter = asyncio.Event(), asyncio.Event()
    identities, qualified, stages, durable = {}, {}, {}, []
    tasks = []
    real_commit = SqlAlchemyTransactionProcessingUnitOfWork.commit
    real_lock = SqlAlchemyCostBasisProcessingStateRepository.acquire_cost_basis_processing_lock
    real_qualify = fee_cost_repository.load_qualified_transaction_fee_sources

    async def observe_qualification(*args, **kwargs):
        result = await real_qualify(*args, **kwargs)
        qualified[asyncio.current_task().get_name()] = result
        return result

    async def observe_lock(repository, portfolio_id, security_id):
        name = asyncio.current_task().get_name()
        if name in {"core795-holder", "core795-waiter"}:
            identities[name] = await _core795_backend(repository._session)
            if name == "core795-waiter":
                waiter_lock_attempt.set()
        await real_lock(repository, portfolio_id, security_id)

    async def hold_actual_commit(uow):
        name = asyncio.current_task().get_name()
        if name in {"core795-holder", "core795-waiter"}:
            assert uow._session is not None and not uow._committed
            stages[name] = await _core795_snapshot(uow._session)
            assert stages[name]["cashflows"] != baseline["cashflows"]
            assert stages[name]["position_lot_state"] != baseline["position_lot_state"]
            assert stages[name]["processed_events"] != baseline["processed_events"]
            assert stages[name]["outbox_events"] != baseline["outbox_events"]
            # Source-cut flush is deliberately still pending at this original boundary.
            assert (
                stages[name]["portfolio_cashflow_source_cuts"]
                == baseline["portfolio_cashflow_source_cuts"]
            )
            assert (
                stages[name]["portfolio_cashflow_source_cut_refresh_queue"]
                != baseline["portfolio_cashflow_source_cut_refresh_queue"]
            )
            assert qualified[name]
            for projection in qualified[name].values():
                assert projection == {
                    "brokerage": Decimal(1),
                    "stamp_duty": Decimal(0),
                    "exchange_fee": Decimal(2),
                    "gst": None,
                    "other_fees": Decimal(0),
                    "trade_fee": Decimal(3),
                }
            (holder_ready if name == "core795-holder" else waiter_ready).set()
            await asyncio.wait_for(
                (release_holder if name == "core795-holder" else release_waiter).wait(), 15
            )
        await real_commit(uow)  # Unmodified flush and durable commit, never a mocked success.
        durable.append(name)

    monkeypatch.setattr(
        fee_cost_repository, "load_qualified_transaction_fee_sources", observe_qualification
    )
    monkeypatch.setattr(
        SqlAlchemyCostBasisProcessingStateRepository,
        "acquire_cost_basis_processing_lock",
        observe_lock,
    )
    monkeypatch.setattr(SqlAlchemyTransactionProcessingUnitOfWork, "commit", hold_actual_commit)

    async def process(event, suffix):
        return await process_booked_transaction(
            context=context,
            event=event,
            event_id=f"transactions.persisted-core795-{suffix}",
            correlation_id=f"core795-{suffix}",
        )

    try:
        holder = asyncio.create_task(process(events[0], "holder"), name="core795-holder")
        tasks.append(holder)
        await wait_for_task_signal(holder, holder_ready, timeout=10)
        waiter = asyncio.create_task(process(events[1], "waiter"), name="core795-waiter")
        tasks.append(waiter)
        await wait_for_task_signal(waiter, waiter_lock_attempt, timeout=10)
        evidence = await _core795_wait_for_same_key_block(
            waiter,
            context.session_factory,
            identities["core795-holder"],
            identities["core795-waiter"],
            cost_basis_processing_lock_key(events[0].portfolio_id, events[0].security_id),
        )
        assert evidence  # A qualified source is not durable contender financial work.
        async with context.session_factory() as observer:
            assert await _core795_snapshot(observer) == baseline
        holder.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(holder, 10)
        await wait_for_task_signal(waiter, waiter_ready, timeout=10)
        assert "core795-holder" not in durable
        async with context.session_factory() as observer:
            assert await _core795_snapshot(observer) == baseline
            assert identities["core795-holder"]["pid"] not in await observer.scalar(
                text("SELECT pg_blocking_pids(:pid)"), {"pid": identities["core795-waiter"]["pid"]}
            )
        release_waiter.set()
        assert (await asyncio.wait_for(waiter, 10)).status is TransactionProcessingStatus.PROCESSED
        assert durable.count("core795-waiter") == 1
        await _core795_assert_cancelled_delivery_absent(
            context.session_factory, events[0], baseline
        )
        await _core795_assert_financial_once(
            context.session_factory, [events[1]], source_cohort=events
        )
        async with context.session_factory() as observer:
            committed = await _core795_snapshot(observer)
        assert (
            await process(events[1], "duplicate")
        ).status is TransactionProcessingStatus.DUPLICATE
        async with context.session_factory() as observer:
            assert await _core795_snapshot(observer) == committed
        assert (
            await process(events[0], "cancelled-followup")
        ).status is TransactionProcessingStatus.PROCESSED
        await _core795_assert_financial_once(context.session_factory, events, source_cohort=events)
        async with context.session_factory() as observer:
            final = await _core795_snapshot(observer)
        assert (
            await process(events[0], "cancelled-duplicate")
        ).status is TransactionProcessingStatus.DUPLICATE
        async with context.session_factory() as observer:
            assert await _core795_snapshot(observer) == final
    finally:
        primary = sys.exception()
        release_holder.set()
        release_waiter.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        try:
            outcomes = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 10)
        except BaseException as cleanup_error:
            if primary is not None:
                primary.add_note(f"owned-task cleanup failed: {cleanup_error!r}")
            else:
                raise
        else:
            if primary is None:
                for outcome in outcomes:
                    if isinstance(outcome, BaseException) and not isinstance(
                        outcome, asyncio.CancelledError
                    ):
                        raise outcome


@pytest.mark.parametrize("later_damage", ["fee", "malformed"])
async def test_later_bad_raw_fee_authority_rolls_back_complete_combined_uow(
    clean_db,
    async_db_session,
    later_damage,
):
    events = await _core795_seed(async_db_session, "PORT-CORE795-BAD", later_bad=later_damage)
    context = transaction_processing_test_context(async_db_session)
    async with context.session_factory() as observer:
        baseline = await _core795_snapshot(observer)
    with pytest.raises(ReprocessingReplayError) as failure:
        await process_booked_transaction(
            context=context,
            event=events[0],
            event_id="transactions.persisted-core795-bad",
            correlation_id="core795-bad",
        )
    source_failure = failure.value
    assert source_failure.reason_code == TRANSACTION_REPLAY_SOURCE_INVALID
    assert str(source_failure) == "Canonical transaction fee source is unavailable or conflicting"
    assert source_failure.published_record_count == 0
    assert source_failure.failed_transaction_ids == [events[0].transaction_id]
    if later_damage == "fee":
        assert type(source_failure.__cause__) is ValueError
        assert "Conflicting retained raw transaction authority" in str(source_failure.__cause__)
    else:
        assert isinstance(source_failure.__cause__, ValidationError)
    async with context.session_factory() as observer:
        assert await _core795_snapshot(observer) == baseline
    # Bad precommitted ingress remains: never delete it to manufacture recovery.
