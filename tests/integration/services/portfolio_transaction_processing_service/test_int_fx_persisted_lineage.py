"""PostgreSQL proof for final-row foreign-exchange calculation lineage."""

import asyncio
import importlib
import json
import os
import subprocess
from dataclasses import fields, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from portfolio_common.database_models import (
    AverageCostPoolState,
    Cashflow,
    LotBasisTransferReceiptRecord,
    LotDisposalReceiptRecord,
    OutboxEvent,
    PipelineStageState,
    PositionHistory,
    PositionLotState,
    PositionState,
    ProcessedEvent,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.calculation_lineage import (
    calculation_lineage_binds_output,
    canonical_content_hash,
)
from portfolio_common.domain.transaction import (
    TRANSACTION_PAYLOAD_MATERIAL_FIELDS,
    transaction_payload_fingerprint,
)
from portfolio_common.event_mapping import transaction_event_v1_payload
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)
from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingIntent,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.application.foreign_exchange_processing import (  # noqa: E501
    book_foreign_exchange_transaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    build_fx_processed_transaction,
    fx_booked_transaction_output_payload,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx.persisted_return import (  # noqa: E501
    FxBookingContext,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisTransactionRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.reference_data_repository import (  # noqa: E501
    SqlAlchemyCostBasisReferenceDataRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.transaction_repository import (  # noqa: E501
    _to_persisted_booked_transaction,
)
from tests.test_support.transaction_processing import (
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


async def _fx_application_snapshot(factory):
    models = (
        DBTransaction,
        TransactionCost,
        PositionLotState,
        AverageCostPoolState,
        Cashflow,
        PositionHistory,
        PositionState,
        ProcessedEvent,
        PipelineStageState,
        LotDisposalReceiptRecord,
        LotBasisTransferReceiptRecord,
        OutboxEvent,
    )
    async with factory() as verification:
        snapshot = {}
        for model in models:
            table = model.__table__
            rows = (
                (
                    await verification.execute(
                        select(*table.columns).order_by(*table.primary_key.columns)
                    )
                )
                .mappings()
                .all()
            )
            snapshot[table.name] = [dict(row) for row in rows]
        print(
            "FX_UOW_SNAPSHOT",
            {
                "pid": await verification.scalar(select(func.pg_backend_pid())),
                "tables": {
                    name: {"count": len(rows), "hash": canonical_content_hash(rows)}
                    for name, rows in snapshot.items()
                },
            },
        )
        return snapshot


def _fx_owned_runtime_identity():
    project = os.environ["COMPOSE_PROJECT_NAME"]
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=" + project,
            "--filter",
            "label=com.docker.compose.service=postgres",
            "-q",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    ids = result.stdout.splitlines()
    assert len(ids) == 1
    result = subprocess.run(
        ["docker", "inspect", ids[0]], check=True, capture_output=True, text=True
    )
    container = json.loads(result.stdout)[0]
    assert container["Config"]["Labels"]["com.docker.compose.project"] == project
    print(
        "FX_UOW_RUNTIME",
        {
            "project": project,
            "container": container["Id"],
            "image_id": container["Image"],
            "image_reference": container["Config"]["Image"],
        },
    )


@pytest.mark.parametrize("case", ["physical_duplicate", "semantic_duplicate", "faulting_winner"])
async def test_fx_application_competing_delivery_uses_real_claim_wait_and_uow(
    clean_db, async_db_session: AsyncSession, monkeypatch, case
):
    _fx_owned_runtime_identity()
    incoming = replace(_fx_transaction(source_system="ORIGINAL"), fx_realized_pnl_mode="NONE")
    event = TransactionEvent(
        **{
            field.name: getattr(incoming, field.name)
            for field in fields(incoming)
            if field.name in TransactionEvent.model_fields
            and getattr(incoming, field.name) is not None
        }
    )
    async_db_session.add(portfolio_record(incoming.portfolio_id))
    await async_db_session.flush()
    assert (
        await TransactionDBRepository(async_db_session).create_or_update_transaction(event)
    ).inserted
    async_db_session.add(
        OutboxEvent(
            aggregate_type="RawTransaction",
            aggregate_id=incoming.portfolio_id,
            event_type="RawTransactionPersisted",
            topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            payload=transaction_event_v1_payload(event),
        )
    )
    await async_db_session.commit()
    winner_context = transaction_processing_test_context(async_db_session)
    loser_context = transaction_processing_test_context(async_db_session)
    before = await _fx_application_snapshot(winner_context.session_factory)
    winner_written, loser_entered, loser_claimed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    release_winner, release_loser = asyncio.Event(), asyncio.Event()
    pids, writes = {}, {"fx-winner": 0, "fx-loser": 0}
    original_claim = IdempotencyRepository.claim_semantic_event_processing
    original_write = SqlAlchemyCostBasisTransactionRepository.upsert_booked_transaction

    async def observe_claim(repository, **kwargs):
        task = asyncio.current_task()
        name = task.get_name() if task else "unknown"
        if kwargs["service_name"] != "portfolio-transaction-processing" or name not in writes:
            return await original_claim(repository, **kwargs)
        pids[name] = await repository.db.scalar(select(func.pg_backend_pid()))
        if name == "fx-loser":
            loser_entered.set()
        outcome = await original_claim(repository, **kwargs)
        if name == "fx-loser" and case == "faulting_winner":
            loser_claimed.set()
            await release_loser.wait()
        return outcome

    async def observe_write(repository, transaction, **kwargs):
        persisted = await original_write(repository, transaction, **kwargs)
        task = asyncio.current_task()
        name = task.get_name() if task else "unknown"
        if transaction.transaction_id == incoming.transaction_id and name in writes:
            writes[name] += 1
            if name == "fx-winner" and writes[name] == 2:
                winner_written.set()
                await release_winner.wait()
                if case == "faulting_winner":
                    raise RuntimeError("injected-concurrent-second-fx-write")
        return persisted

    monkeypatch.setattr(IdempotencyRepository, "claim_semantic_event_processing", observe_claim)
    monkeypatch.setattr(
        SqlAlchemyCostBasisTransactionRepository, "upsert_booked_transaction", observe_write
    )
    event_id = "FX-CONCURRENT-WINNER"
    loser_id = "FX-CONCURRENT-OTHER" if case == "semantic_duplicate" else event_id
    tasks = []
    try:
        async with asyncio.timeout(20):
            winner = asyncio.create_task(
                process_booked_transaction(
                    context=winner_context,
                    event=event,
                    event_id=event_id,
                    correlation_id="WINNER",
                ),
                name="fx-winner",
            )
            tasks.append(winner)
            await winner_written.wait()
            loser = asyncio.create_task(
                process_booked_transaction(
                    context=loser_context,
                    event=event,
                    event_id=loser_id,
                    correlation_id="LOSER",
                ),
                name="fx-loser",
            )
            tasks.append(loser)
            await loser_entered.wait()
            assert pids["fx-winner"] != pids["fx-loser"]
            async with winner_context.session_factory() as observer:
                while True:
                    await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    wait = (
                        (
                            await observer.execute(
                                text(
                                    "SELECT pid,state,query,wait_event_type,wait_event,"
                                    "pg_blocking_pids(pid) AS blockers FROM pg_stat_activity "
                                    "WHERE pid=:pid"
                                ),
                                {"pid": pids["fx-loser"]},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    if pids["fx-winner"] in wait["blockers"]:
                        break
                    await asyncio.sleep(0.01)
                assert wait["wait_event_type"] == "Lock"
                assert "processed_events" in wait["query"].lower()
                assert "insert" in wait["query"].lower()
                locks = (
                    (
                        await observer.execute(
                            text(
                                "SELECT pid,locktype,mode,granted,"
                                "relation::regclass::text AS relation,transactionid,classid,objid "
                                "FROM pg_locks WHERE pid IN (:winner,:loser)"
                            ),
                            {"winner": pids["fx-winner"], "loser": pids["fx-loser"]},
                        )
                    )
                    .mappings()
                    .all()
                )
                assert any(
                    lock["pid"] == pids["fx-loser"] and not lock["granted"] for lock in locks
                )
                print(
                    "FX_CONCURRENT_WAIT",
                    {
                        "case": case,
                        "pids": pids,
                        "wait": dict(wait),
                        "locks": [dict(lock) for lock in locks],
                    },
                )
            release_winner.set()
            if case == "faulting_winner":
                with pytest.raises(RuntimeError, match="injected-concurrent-second-fx-write"):
                    await winner
                await loser_claimed.wait()
                assert writes["fx-winner"] == 2 and writes["fx-loser"] == 0
                assert await _fx_application_snapshot(winner_context.session_factory) == before
                print(
                    "FX_CONCURRENT_ROLLBACK",
                    "winner rolled back; loser owns uncommitted claim "
                    "but has made no financial writes",
                )
                release_loser.set()
                assert (await loser).status is TransactionProcessingStatus.PROCESSED
            else:
                assert (await winner).status is TransactionProcessingStatus.PROCESSED
                assert (await loser).status is TransactionProcessingStatus.DUPLICATE
                assert writes == {"fx-winner": 2, "fx-loser": 0}
            after = await _fx_application_snapshot(winner_context.session_factory)
            assert after != before
            assert [
                row for row in after["outbox_events"] if row["aggregate_type"] == "RawTransaction"
            ] == before["outbox_events"]
            assert len(after["transactions"]) == 1
            assert len(after["position_history"]) == len(after["position_state"]) == 1
            assert (
                len(
                    [
                        row
                        for row in after["processed_events"]
                        if row["service_name"] == "portfolio-transaction-processing"
                    ]
                )
                == 1
            )
            assert after["pipeline_stage_state"] and not after["cashflows"]
            async with winner_context.session_factory() as verification:
                row = (
                    await verification.execute(
                        select(DBTransaction).where(
                            DBTransaction.transaction_id == incoming.transaction_id
                        )
                    )
                ).scalar_one()
                final = _to_persisted_booked_transaction(row, tenant_id=incoming.tenant_id)
                assert calculation_lineage_binds_output(
                    final.calculation_lineage,
                    output_payload=fx_booked_transaction_output_payload(final),
                )
            for retry_id in (event_id, loser_id):
                retry = await process_booked_transaction(
                    context=winner_context, event=event, event_id=retry_id, correlation_id="RETRY"
                )
                assert retry.status is TransactionProcessingStatus.DUPLICATE
                assert await _fx_application_snapshot(winner_context.session_factory) == after
            async with winner_context.session_factory() as observer:
                active = (
                    (
                        await observer.execute(
                            text(
                                "SELECT pid,state,query FROM pg_stat_activity "
                                "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                                "AND backend_type='client backend' AND state<>'idle'"
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
                assert not active
                print("FX_CONCURRENT_QUIESCENCE", list(active))
    finally:
        release_winner.set()
        release_loser.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("mode", ["NONE", "UPSTREAM_PROVIDED"])
@pytest.mark.parametrize("route", ["standard", "repair"])
@pytest.mark.parametrize("fault_write", [1, 2])
@pytest.mark.parametrize("component", ["FX_CONTRACT_OPEN", "FX_CASH_SETTLEMENT_BUY"])
async def test_fx_application_uow_rolls_back_actual_write_fault_then_retries(
    clean_db, async_db_session: AsyncSession, monkeypatch, mode, route, fault_write, component
):
    await _assert_fx_application_uow_fault(
        async_db_session, monkeypatch, mode, route, fault_write, component
    )


async def test_fx_application_uow_explicit_original_contract_linkage_control(
    clean_db, async_db_session: AsyncSession, monkeypatch
):
    await _assert_fx_application_uow_fault(
        async_db_session,
        monkeypatch,
        "UPSTREAM_PROVIDED",
        "standard",
        1,
        "FX_CONTRACT_OPEN",
        explicit_source_linkage=True,
    )


@pytest.mark.parametrize("route", ["standard", "repair"])
async def test_fx_application_uow_omitted_mode_preserves_default_after_second_write_fault(
    clean_db, async_db_session: AsyncSession, monkeypatch, route
):
    await _assert_fx_application_uow_fault(
        async_db_session, monkeypatch, None, route, 2, "FX_CONTRACT_OPEN"
    )


async def _assert_fx_application_uow_fault(
    async_db_session,
    monkeypatch,
    mode,
    route,
    fault_write,
    component,
    *,
    explicit_source_linkage=False,
):
    _fx_owned_runtime_identity()
    incoming = replace(
        _fx_transaction(source_system="ORIGINAL"),
        fx_realized_pnl_mode=mode,
        realized_capital_pnl_local=None,
        realized_total_pnl_local=None,
        realized_capital_pnl_base=Decimal("0"),
        realized_total_pnl_base=None,
        realized_fx_pnl_local=Decimal("2.5") if mode == "UPSTREAM_PROVIDED" else None,
        realized_fx_pnl_base=Decimal("2.5") if mode == "UPSTREAM_PROVIDED" else None,
    )
    if component == "FX_CASH_SETTLEMENT_BUY":
        incoming = replace(
            incoming,
            instrument_id="CASH-USD-FX-UOW",
            security_id="CASH-USD-FX-UOW",
            settlement_cash_account_id="ACCOUNT-USD-FX-UOW",
            settlement_cash_instrument_id="CASH-USD-FX-UOW",
            component_type=component,
            fx_cash_leg_role="BUY",
            linked_fx_cash_leg_id="FX-COMP-SELL-001",
        )
    if explicit_source_linkage:
        incoming = replace(incoming, fx_contract_open_transaction_id=incoming.transaction_id)
    event = TransactionEvent(
        **{
            field.name: getattr(incoming, field.name)
            for field in fields(incoming)
            if field.name in TransactionEvent.model_fields
            and getattr(incoming, field.name) is not None
        }
    )
    async_db_session.add(portfolio_record(incoming.portfolio_id))
    await async_db_session.flush()
    if component == "FX_CASH_SETTLEMENT_BUY":
        async_db_session.add(
            instrument_record(
                incoming.security_id,
                name="FX UOW USD settlement cash",
                isin="CASHUSD-FX-UOW",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            )
        )
        await async_db_session.flush()
        async_db_session.add(
            cash_account_record(
                incoming.settlement_cash_account_id,
                portfolio_id=incoming.portfolio_id,
                security_id=incoming.security_id,
                account_currency="USD",
            )
        )
        await async_db_session.flush()
        references = SqlAlchemyCostBasisReferenceDataRepository(async_db_session)
        lookup = dict(
            portfolio_id=incoming.portfolio_id,
            tenant_id=incoming.tenant_id,
            cash_account_id=incoming.settlement_cash_account_id,
            as_of_date=incoming.settlement_date.date(),
        )
        cash_reference = await references.get_settlement_cash_account_reference(**lookup)
        assert cash_reference is not None
        assert cash_reference.security_id == incoming.security_id
        assert cash_reference.account_currency == cash_reference.instrument_currency == "USD"
        assert cash_reference.instrument_product_type == "CASH"
        assert (
            await references.get_settlement_cash_account_reference(
                **(lookup | {"portfolio_id": "PORT-FX-UOW-WRONG-OWNER"})
            )
            is None
        )
        print(
            "FX_UOW_SCOPE",
            "account ownership verified by native reference adapter; not generated-cash route",
        )
        print("FX_UOW_CASH_SETUP", event.model_dump(mode="json"))
    outcome = await TransactionDBRepository(async_db_session).create_or_update_transaction(event)
    assert outcome.inserted
    raw_payload = transaction_event_v1_payload(event)
    if mode is None:
        assert "fx_realized_pnl_mode" not in event.model_fields_set
        raw_payload.pop("fx_realized_pnl_mode")
        assert event.fx_realized_pnl_mode is None
        assert "fx_realized_pnl_mode" not in raw_payload
        assert {
            name: raw_payload[name]
            for name in (
                "realized_capital_pnl_local",
                "realized_total_pnl_local",
                "realized_capital_pnl_base",
                "realized_total_pnl_base",
                "realized_fx_pnl_local",
                "realized_fx_pnl_base",
            )
        } == {
            "realized_capital_pnl_local": None,
            "realized_total_pnl_local": None,
            "realized_capital_pnl_base": "0",
            "realized_total_pnl_base": None,
            "realized_fx_pnl_local": None,
            "realized_fx_pnl_base": None,
        }
    async_db_session.add(
        OutboxEvent(
            aggregate_type="RawTransaction",
            aggregate_id=incoming.portfolio_id,
            event_type="RawTransactionPersisted",
            topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            payload=raw_payload,
        )
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    booking = importlib.import_module(
        "src.services.portfolio_transaction_processing_service.app.application."
        "foreign_exchange_processing.booking"
    )
    processing = importlib.import_module(
        "src.services.portfolio_transaction_processing_service.app.application.process_transaction"
    )
    semantics = importlib.import_module(
        "src.services.portfolio_transaction_processing_service.app.domain.transaction.semantic_identity"
    )
    retention = importlib.import_module(
        "src.services.portfolio_transaction_processing_service.app.domain.transaction.fx.persisted_return"
    )
    qualify_source = booking.qualify_fx_booking_source
    admit_group = processing._admitted_position_group

    def describe_fields(left, right):
        return {
            name: {"before": repr(left.get(name)), "after": repr(right.get(name))}
            for name in left.keys() | right.keys()
            if left.get(name) != right.get(name)
        }

    def observe_qualification(transaction, witness, booking_context):
        if witness is not None:
            original_material = retention.fx_source_material(incoming)
            durable_material = retention.fx_source_material(witness.durable_before)
            prepared_material = retention.fx_source_material(transaction)
            print(
                "FX_UOW_SOURCE_BOUNDARY",
                {
                    "explicit_original_linkage": explicit_source_linkage,
                    "route": route,
                    "context": repr(booking_context),
                    "original_to_durable": describe_fields(original_material, durable_material),
                    "durable_to_prepared": describe_fields(durable_material, prepared_material),
                    "original_fingerprint": transaction_payload_fingerprint(original_material),
                    "raw_fingerprint": witness.raw_source.material_fingerprint
                    if witness.raw_source
                    else None,
                    "prepared_fingerprint": transaction_payload_fingerprint(prepared_material),
                },
            )
        return qualify_source(transaction, witness, booking_context)

    def observe_group(command, identity, members, **kwargs):
        root = semantics._material_payload(command.transaction, include_source_booked_fx=False)
        for member in members:
            if member.transaction_id == command.transaction.transaction_id:
                material = semantics._material_payload(member, include_source_booked_fx=False)
                print(
                    "FX_UOW_POSITION_BOUNDARY",
                    {
                        "route": route,
                        "admission": repr(identity),
                        "root_identity": repr(
                            semantics.build_transaction_semantic_identity(command.transaction)
                        ),
                        "member_identity": repr(
                            semantics.build_transaction_semantic_identity(member)
                        ),
                        "differences": describe_fields(root, material),
                        "root_epoch": command.transaction.epoch,
                        "member_epoch": member.epoch,
                    },
                )
        return admit_group(command, identity, members, **kwargs)

    monkeypatch.setattr(booking, "qualify_fx_booking_source", observe_qualification)
    monkeypatch.setattr(processing, "_admitted_position_group", observe_group)
    if route == "repair":
        initial = await process_booked_transaction(
            context=context, event=event, event_id="FX-UOW-FIRST", correlation_id="FX-UOW-FIRST"
        )
        assert initial.status is TransactionProcessingStatus.PROCESSED
    before = await _fx_application_snapshot(context.session_factory)
    written = []
    source_loads = {"preloaded": 0, "fallback": 0}
    preloaded = SqlAlchemyCostBasisTransactionRepository.load_booked_transaction_with_fx_witness
    fallback = SqlAlchemyCostBasisTransactionRepository.load_fx_retention_witness

    async def observe_preloaded(repository, transaction):
        source_loads["preloaded"] += 1
        return await preloaded(repository, transaction)

    async def observe_fallback(repository, transaction):
        source_loads["fallback"] += 1
        return await fallback(repository, transaction)

    original = SqlAlchemyCostBasisTransactionRepository.upsert_booked_transaction

    async def write_then_fault(repository, transaction, **kwargs):
        persisted = await original(repository, transaction, **kwargs)
        if transaction.transaction_id == incoming.transaction_id:
            written.append(persisted)
            print(
                "FX_UOW_ACTUAL_WRITE",
                {
                    "write": len(written),
                    "session": id(repository.db),
                    "pid": await repository.db.scalar(select(func.pg_backend_pid())),
                    "lineage": persisted.calculation_lineage.lineage_payload(),
                    "created_at": repr(persisted.created_at),
                },
            )
            if len(written) == fault_write:
                raise RuntimeError("injected-after-fx-write-" + str(fault_write))
        return persisted

    intent = (
        TransactionProcessingIntent.REPAIR
        if route == "repair"
        else TransactionProcessingIntent.STANDARD
    )
    kwargs = dict(
        context=context,
        event=event,
        event_id="FX-UOW-FAULT",
        correlation_id="FX-UOW-FAULT",
        processing_intent=intent,
        repair_delivery_id="FX-UOW-REPAIR" if route == "repair" else None,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            SqlAlchemyCostBasisTransactionRepository, "upsert_booked_transaction", write_then_fault
        )
        patch.setattr(
            SqlAlchemyCostBasisTransactionRepository,
            "load_booked_transaction_with_fx_witness",
            observe_preloaded,
        )
        patch.setattr(
            SqlAlchemyCostBasisTransactionRepository, "load_fx_retention_witness", observe_fallback
        )
        with pytest.raises(RuntimeError, match="injected-after-fx-write-" + str(fault_write)):
            await process_booked_transaction(**kwargs)
    assert len(written) == fault_write
    assert source_loads == (
        {"preloaded": 1, "fallback": 0} if route == "standard" else {"preloaded": 0, "fallback": 1}
    )
    print("FX_UOW_SOURCE_ROUTE", source_loads)
    assert await _fx_application_snapshot(context.session_factory) == before
    retry = await process_booked_transaction(**kwargs)
    assert retry.status is TransactionProcessingStatus.PROCESSED
    after = await _fx_application_snapshot(context.session_factory)
    assert after != before
    original_raw = [
        row for row in before["outbox_events"] if row["aggregate_type"] == "RawTransaction"
    ]
    assert original_raw
    assert [
        row for row in after["outbox_events"] if row["aggregate_type"] == "RawTransaction"
    ] == original_raw
    assert after["transactions"][0]["calculation_lineage"] is not None
    assert after["transactions"][0]["gross_cost"] == Decimal(0)
    async with context.session_factory() as verification:
        final_row = (
            await verification.execute(
                select(DBTransaction).where(DBTransaction.transaction_id == incoming.transaction_id)
            )
        ).scalar_one()
        final_booked = _to_persisted_booked_transaction(final_row, tenant_id=incoming.tenant_id)
        if mode is None:
            assert final_booked.fx_realized_pnl_mode == "NONE"
        assert calculation_lineage_binds_output(
            final_booked.calculation_lineage,
            output_payload=fx_booked_transaction_output_payload(final_booked),
        )
        print("FX_UOW_FINAL_RECEIPT", final_booked.calculation_lineage.lineage_payload())
    assert after["position_history"] and after["position_state"]
    assert after["processed_events"] and after["pipeline_stage_state"]
    assert len(after["outbox_events"]) > len(before["outbox_events"])
    if component == "FX_CASH_SETTLEMENT_BUY":
        assert after["cashflows"] and retry.cashflow_record_count == 1
        assert after["cashflows"][0]["amount"] == incoming.buy_amount
    else:
        assert not after["cashflows"] and retry.cashflow_record_count == 0
        print("FX_UOW_SCOPE", "contract-open no-cash; physical cash rollback not certified")
    assert not after["position_lot_state"] and not after["average_cost_pool_state"]
    print("FX_UOW_SCOPE", "FX baseline costs in transaction row; equity lots/pools not applicable")
    duplicate = await process_booked_transaction(**kwargs)
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE
    assert await _fx_application_snapshot(context.session_factory) == after
    async with context.session_factory() as verification:
        active = (
            (
                await verification.execute(
                    text(
                        "SELECT pid,state,query FROM pg_stat_activity "
                        "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                        "AND backend_type='client backend' AND state<>'idle'"
                    )
                )
            )
            .mappings()
            .all()
        )
        print("FX_UOW_QUIESCENCE", [dict(row) for row in active])
        assert not active


def _fx_transaction(*, source_system: str | None) -> BookedTransaction:
    return BookedTransaction(
        transaction_id="FX-LINEAGE-REPROCESS-001",
        portfolio_id="PORT-FX-LINEAGE-001",
        tenant_id="tenant-test",
        instrument_id="FXC-EURUSD-LINEAGE-001",
        security_id="FXC-EURUSD-LINEAGE-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        component_id="FX-COMP-LINEAGE-001",
        linked_component_ids=("FX-COMP-BUY-001", "FX-COMP-SELL-001"),
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("1095000"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        fx_rate_quote_convention="QUOTE_PER_BASE",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        economic_event_id="EVT-FX-LINEAGE-001",
        linked_transaction_group_id="LTG-FX-LINEAGE-001",
        calculation_policy_id="FX_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        fx_contract_id="FXC-EURUSD-LINEAGE-001",
        spot_exposure_model="NONE",
        fx_realized_pnl_mode="NONE",
        source_system=source_system,
    )


async def test_fx_initial_none_fresh_insert_binds_server_creation_timestamp(
    clean_db, async_db_session: AsyncSession
) -> None:
    incoming = _fx_transaction(source_system=None)
    async_db_session.add(portfolio_record(incoming.portfolio_id))
    await async_db_session.commit()
    result = await book_foreign_exchange_transaction(
        transaction=incoming,
        transaction_persistence=SqlAlchemyCostBasisTransactionRepository(async_db_session),
        booking_context=FxBookingContext(initial_publication=True, admitted_epoch=None),
    )
    await async_db_session.commit()
    row = (
        await async_db_session.execute(
            select(DBTransaction).where(DBTransaction.transaction_id == incoming.transaction_id)
        )
    ).scalar_one()
    assert result.transaction.created_at == row.created_at
    assert row.created_at is not None
    assert row.calculation_lineage == result.transaction.calculation_lineage.lineage_payload()
    assert calculation_lineage_binds_output(
        result.transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(result.transaction),
    )


@pytest.mark.parametrize("date_style", ["wire", "microseconds", "equivalent_offset"])
@pytest.mark.parametrize("tamper", [None, "date", "offset_instant", "source_system"])
async def test_fx_initial_upstream_persisted_raw_keeps_original_presence_and_timestamp(
    clean_db, async_db_session: AsyncSession, date_style: str, tamper: str | None
) -> None:
    incoming = replace(
        _fx_transaction(source_system="ORIGINAL"),
        fx_realized_pnl_mode="UPSTREAM_PROVIDED",
        realized_capital_pnl_local=None,
        realized_fx_pnl_local=Decimal("2.5"),
        realized_total_pnl_local=None,
        realized_capital_pnl_base=Decimal("0"),
        realized_fx_pnl_base=Decimal("2.5"),
        realized_total_pnl_base=None,
    )
    event = TransactionEvent(
        **{
            field.name: getattr(incoming, field.name)
            for field in fields(incoming)
            if field.name in TransactionEvent.model_fields
            and getattr(incoming, field.name) is not None
        }
    )
    async_db_session.add(portfolio_record(incoming.portfolio_id))
    await async_db_session.flush()
    outcome = await TransactionDBRepository(async_db_session).create_or_update_transaction(event)
    assert outcome.inserted
    raw_payload = transaction_event_v1_payload(event)
    if date_style == "microseconds":
        raw_payload["transaction_date"] = "2026-04-01T09:00:00.000000Z"
        raw_payload["settlement_date"] = "2026-07-01T09:00:00.000000Z"
    elif date_style == "equivalent_offset":
        raw_payload["transaction_date"] = "2026-04-01T17:00:00+08:00"
        raw_payload["settlement_date"] = "2026-07-01T17:00:00+08:00"
    if tamper == "date":
        raw_payload["transaction_date"] = "2026-04-02T09:00:00Z"
    elif tamper == "offset_instant":
        raw_payload["transaction_date"] = "2026-04-01T09:00:00+08:00"
    elif tamper == "source_system":
        raw_payload["source_system"] = "FOREIGN"
    async_db_session.add(
        OutboxEvent(
            aggregate_type="RawTransaction",
            aggregate_id=incoming.portfolio_id,
            event_type="RawTransactionPersisted",
            topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            payload=raw_payload,
        )
    )
    await async_db_session.commit()
    before_timestamp = (
        await async_db_session.execute(
            select(DBTransaction.created_at).where(
                DBTransaction.transaction_id == incoming.transaction_id
            )
        )
    ).scalar_one()
    print(
        "FX_INITIAL_RAW_IDENTITY",
        {
            "ledger": (
                await async_db_session.execute(
                    select(DBTransaction.payload_fingerprint).where(
                        DBTransaction.transaction_id == incoming.transaction_id
                    )
                )
            ).scalar_one(),
            "raw": transaction_payload_fingerprint(raw_payload),
            "typed_dates": (repr(event.transaction_date), repr(event.settlement_date)),
            "wire_dates": (raw_payload["transaction_date"], raw_payload["settlement_date"]),
        },
    )
    if tamper is not None:
        with pytest.raises(ValueError, match="original raw fingerprint"):
            await book_foreign_exchange_transaction(
                transaction=incoming,
                transaction_persistence=SqlAlchemyCostBasisTransactionRepository(async_db_session),
                booking_context=FxBookingContext(initial_publication=True, admitted_epoch=None),
            )
        await async_db_session.rollback()
        factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
        async with factory() as verification:
            row = (
                await verification.execute(
                    select(DBTransaction).where(
                        DBTransaction.transaction_id == incoming.transaction_id
                    )
                )
            ).scalar_one()
            assert row.calculation_lineage is None
            assert row.source_system == incoming.source_system
            assert row.created_at == before_timestamp
        return
    result = await book_foreign_exchange_transaction(
        transaction=incoming,
        transaction_persistence=SqlAlchemyCostBasisTransactionRepository(async_db_session),
        booking_context=FxBookingContext(initial_publication=True, admitted_epoch=None),
    )
    await async_db_session.commit()
    assert result.transaction.created_at == before_timestamp
    assert result.transaction.calculation_lineage is not None
    expected = build_fx_processed_transaction(replace(incoming, created_at=before_timestamp))
    assert result.transaction.calculation_lineage.input_content_hash == (
        expected.calculation_lineage.input_content_hash
    )
    assert calculation_lineage_binds_output(
        result.transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(result.transaction),
    )
    assert result.transaction.calculation_lineage.input_content_hash != (
        build_fx_processed_transaction(result.transaction).calculation_lineage.input_content_hash
    )
    replayed = await book_foreign_exchange_transaction(
        transaction=result.transaction,
        transaction_persistence=SqlAlchemyCostBasisTransactionRepository(async_db_session),
        booking_context=FxBookingContext(initial_publication=False, admitted_epoch=None),
    )
    assert replayed.transaction == result.transaction


async def test_fx_reprocessing_receipt_binds_optional_value_retained_by_conflict_update(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    existing = _fx_transaction(source_system="EXISTING_BOOKING_LEDGER")
    async_db_session.add(portfolio_record(existing.portfolio_id))
    async_db_session.add(
        DBTransaction(
            **{
                field.name: value
                for field in fields(existing)
                if field.name in DBTransaction.__table__.columns
                and field.name != "calculation_lineage"
                and (value := getattr(existing, field.name)) is not None
            }
        )
    )
    await async_db_session.commit()

    result = await book_foreign_exchange_transaction(
        transaction=_fx_transaction(source_system=None),
        transaction_persistence=SqlAlchemyCostBasisTransactionRepository(async_db_session),
    )
    durable_row = (
        (
            await async_db_session.execute(
                select(*DBTransaction.__table__.columns).where(
                    DBTransaction.transaction_id == result.transaction.transaction_id
                )
            )
        )
        .mappings()
        .one()
    )

    assert durable_row["source_system"] == "EXISTING_BOOKING_LEDGER"
    assert result.transaction.source_system == durable_row["source_system"]
    assert durable_row["payload_fingerprint"] == transaction_payload_fingerprint(
        {
            field_name: durable_row[field_name]
            for field_name in TRANSACTION_PAYLOAD_MATERIAL_FIELDS
            if field_name in DBTransaction.__table__.columns
        }
        | {
            "transaction_fx_rate": durable_row["transaction_fx_rate"],
            "transaction_fx_rate_origin": durable_row["transaction_fx_rate_origin"],
        }
    )
    assert result.transaction.calculation_lineage is not None
    assert durable_row["calculation_lineage"] == (
        result.transaction.calculation_lineage.lineage_payload()
    )
    assert calculation_lineage_binds_output(
        result.transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(result.transaction),
    )


def _generated_cash_leg(
    *,
    source_system: str | None,
    gross_transaction_amount: Decimal,
    transaction_fx_rate: Decimal = Decimal("2"),
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id="BUY-LINEAGE-001-CASHLEG",
        portfolio_id="PORT-FX-LINEAGE-001",
        tenant_id="tenant-test",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_type="ADJUSTMENT",
        transaction_date=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        quantity=Decimal(0),
        price=Decimal(1),
        gross_transaction_amount=gross_transaction_amount,
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="AUTO_GENERATE",
        originating_transaction_id="BUY-LINEAGE-001",
        originating_transaction_type="BUY",
        link_type="BUY_TO_CASH",
        source_system=source_system,
        transaction_fx_rate=transaction_fx_rate,
        transaction_fx_rate_origin="SOURCE_BOOKED",
    )


async def test_generated_child_fingerprint_uses_post_upsert_durable_economics(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    existing = _generated_cash_leg(
        source_system="EXISTING_BOOKING_LEDGER",
        gross_transaction_amount=Decimal("1080000"),
    )
    async_db_session.add(portfolio_record(existing.portfolio_id))
    preloaded_record = DBTransaction(
        **{
            field.name: value
            for field in fields(existing)
            if field.name in DBTransaction.__table__.columns
            and field.name != "calculation_lineage"
            and (value := getattr(existing, field.name)) is not None
        }
    )
    async_db_session.add(preloaded_record)
    await async_db_session.commit()

    result = await SqlAlchemyCostBasisTransactionRepository(
        async_db_session
    ).upsert_generated_booked_transaction(
        _generated_cash_leg(
            source_system=None,
            gross_transaction_amount=Decimal("1095000"),
        )
    )
    durable_row = (
        (
            await async_db_session.execute(
                select(*DBTransaction.__table__.columns).where(
                    DBTransaction.transaction_id == result.transaction_id
                )
            )
        )
        .mappings()
        .one()
    )

    assert durable_row["source_system"] == "EXISTING_BOOKING_LEDGER"
    assert durable_row["gross_transaction_amount"] == Decimal("1095000")
    assert result.source_system == durable_row["source_system"]
    assert result.gross_transaction_amount == durable_row["gross_transaction_amount"]
    assert durable_row["payload_fingerprint"] == transaction_payload_fingerprint(
        {
            field_name: durable_row[field_name]
            for field_name in TRANSACTION_PAYLOAD_MATERIAL_FIELDS
            if field_name in DBTransaction.__table__.columns
        }
        | {
            "transaction_fx_rate": durable_row["transaction_fx_rate"],
            "transaction_fx_rate_origin": durable_row["transaction_fx_rate_origin"],
        }
    )

    prior_fingerprint = durable_row["payload_fingerprint"]
    await SqlAlchemyCostBasisTransactionRepository(
        async_db_session
    ).upsert_generated_booked_transaction(
        _generated_cash_leg(
            source_system=None,
            gross_transaction_amount=Decimal("1095000"),
            transaction_fx_rate=Decimal("2.5"),
        )
    )
    refreshed = (
        (
            await async_db_session.execute(
                select(*DBTransaction.__table__.columns).where(
                    DBTransaction.transaction_id == result.transaction_id
                )
            )
        )
        .mappings()
        .one()
    )
    assert refreshed["payload_fingerprint"] != prior_fingerprint
    assert refreshed["payload_fingerprint"] == transaction_payload_fingerprint(
        {
            field_name: refreshed[field_name]
            for field_name in TRANSACTION_PAYLOAD_MATERIAL_FIELDS
            if field_name in DBTransaction.__table__.columns
        }
        | {
            "transaction_fx_rate": refreshed["transaction_fx_rate"],
            "transaction_fx_rate_origin": refreshed["transaction_fx_rate_origin"],
        }
    )
