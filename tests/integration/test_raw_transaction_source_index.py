"""Real PostgreSQL index cutover, full original-source lookup and row-lock proof."""

import asyncio
import hashlib
import json
import runpy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common import reprocessing_repository
from portfolio_common.database_models import OutboxEvent
from portfolio_common.reprocessing_repository import (
    _transactions_to_replay_stmt,
    load_transaction_fee_facts,
)
from pydantic import ValidationError
from sqlalchemy import literal, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session

from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay.fee_authority import (  # noqa: E501
    qualify_transaction_fee_source,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    portfolio_record,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.lifecycle]
_INDEX = "ix_outbox_events_raw_transaction_source"
_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/c180b2c3d541_index_raw_transaction_sources.py"
)


def _raw(payload, *, portfolio="RAW-SOURCE", family="RawTransaction", event_type=None, **fields):
    return OutboxEvent(
        aggregate_type=family,
        aggregate_id=portfolio,
        event_type=event_type or "RawTransactionPersisted",
        topic="raw_transactions",
        payload=payload,
        status="PROCESSED",
        **fields,
    )


@pytest.mark.usefixtures("clean_db")
def test_concurrent_migration_preserves_legacy_rows_reuses_valid_and_repairs_invalid(db_engine):
    with Session(db_engine) as session:
        for index, status in enumerate(("PENDING", "FAILED", "PROCESSING", "PROCESSED")):
            row = _raw({"transaction_id": "DUPLICATE", "original": index})
            row.status = status
            session.add(row)
        session.commit()
        before = session.execute(select(OutboxEvent.__table__).order_by(OutboxEvent.id)).all()

    migration = runpy.run_path(str(_MIGRATION))
    _run_migration(db_engine, migration, "downgrade")
    _run_migration(db_engine, migration, "upgrade")
    state, oid = _catalog(db_engine, migration)
    assert state["valid"] and state["ready"]
    assert migration["_matches_index"](state), json.dumps(dict(state))
    _run_migration(db_engine, migration, "upgrade")
    assert _catalog(db_engine, migration)[1] == oid
    _run_migration(db_engine, migration, "downgrade")
    with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        with pytest.raises(DBAPIError):
            connection.execute(
                text(f"CREATE INDEX CONCURRENTLY {_INDEX} ON outbox_events ((1 / (id-id)))")
            )
    # A failed real concurrent build leaves an invalid catalog entry.
    assert not _catalog(db_engine, migration)[0]["valid"]
    _run_migration(db_engine, migration, "upgrade")
    assert migration["_matches_index"](_catalog(db_engine, migration)[0])
    with db_engine.connect() as connection:
        assert (
            connection.execute(select(OutboxEvent.__table__).order_by(OutboxEvent.id)).all()
            == before
        )
    _run_migration(db_engine, migration, "downgrade")
    with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f"CREATE INDEX {_INDEX} ON outbox_events (aggregate_id, id)"))
    with pytest.raises(RuntimeError, match="unexpected catalog shape"):
        _run_migration(db_engine, migration, "upgrade")
    _run_migration(db_engine, migration, "downgrade")
    _run_migration(db_engine, migration, "upgrade")


def _run_migration(engine, migration, operation):
    with engine.connect() as connection:
        migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
        migration[operation]()
        connection.commit()


def _catalog(engine, migration):
    with engine.connect() as connection:
        migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
        state = migration["_index_state"]()
        oid = connection.scalar(text(f"SELECT '{_INDEX}'::regclass::oid"))
        return state, oid


def _long_identifier(prefix):
    return "".join(hashlib.sha256(f"{prefix}-{i}".encode()).hexdigest() for i in range(24))


def _create_old_shape(engine):
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            text(
                f"CREATE INDEX CONCURRENTLY {_INDEX} ON outbox_events "
                "(aggregate_id, (CAST(payload ->> 'transaction_id' AS VARCHAR)), id) "
                "WHERE aggregate_type = 'RawTransaction' "
                "AND event_type = 'RawTransactionPersisted'"
            )
        )


@pytest.mark.usefixtures("clean_db")
def test_unbounded_composite_index_rejects_previously_valid_long_identifiers(db_engine):
    """Retain the old-shape failure as a real PostgreSQL negative control."""
    migration = runpy.run_path(str(_MIGRATION))
    portfolio, transaction = _long_identifier("portfolio"), _long_identifier("transaction")
    _run_migration(db_engine, migration, "downgrade")
    try:
        with Session(db_engine) as session:
            row = _raw({"transaction_id": transaction}, portfolio=portfolio)
            session.add(row)
            session.commit()
            row_id = row.id
        with pytest.raises(DBAPIError, match="index row size.*exceeds.*maximum"):
            _create_old_shape(db_engine)
        assert not _catalog(db_engine, migration)[0]["valid"]
        with Session(db_engine) as session:
            assert session.get(OutboxEvent, row_id).payload["transaction_id"] == transaction
            session.delete(session.get(OutboxEvent, row_id))
            session.commit()
        _run_migration(db_engine, migration, "downgrade")
        _create_old_shape(db_engine)
        with Session(db_engine) as session:
            session.add(_raw({"transaction_id": transaction}, portfolio=portfolio))
            with pytest.raises(DBAPIError, match="index row size.*exceeds.*maximum"):
                session.commit()
            session.rollback()
    finally:
        _run_migration(db_engine, migration, "downgrade")
        _run_migration(db_engine, migration, "upgrade")


@pytest.mark.asyncio
async def test_bounded_index_upgrades_long_originals_and_preserves_loader_results(
    clean_db, db_engine, async_db_session
):
    migration = runpy.run_path(str(_MIGRATION))
    portfolio, transaction = _long_identifier("portfolio"), _long_identifier("transaction")
    _run_migration(db_engine, migration, "downgrade")
    originals = [
        _raw({"transaction_id": transaction, "fee": "1"}, portfolio=portfolio),
        _raw({"transaction_id": transaction, "fee": "99"}, portfolio=portfolio),
    ]
    async_db_session.add_all(originals)
    await async_db_session.commit()
    baseline = (
        (
            await async_db_session.execute(
                select(OutboxEvent.id, OutboxEvent.aggregate_id, OutboxEvent.payload)
                .where(OutboxEvent.aggregate_id == portfolio)
                .order_by(OutboxEvent.id)
            )
        )
        .mappings()
        .all()
    )
    await async_db_session.rollback()
    _run_migration(db_engine, migration, "upgrade")
    state = _catalog(db_engine, migration)[0]
    assert migration["_matches_index"](state), json.dumps(dict(state))
    for lock in (False, True):
        _, rows, _ = await load_transaction_fee_facts(
            async_db_session,
            [{"transaction_id": transaction, "portfolio_id": portfolio}],
            lock_sources=lock,
        )
        assert rows == baseline
        await async_db_session.rollback()
    new_original = _raw({"transaction_id": transaction, "fee": "7"}, portfolio=portfolio)
    async_db_session.add(new_original)
    await async_db_session.commit()
    _, rows, _ = await load_transaction_fee_facts(
        async_db_session, [{"transaction_id": transaction, "portfolio_id": portfolio}]
    )
    assert [r["payload"]["fee"] for r in rows] == ["1", "99", "7"]


@pytest.mark.asyncio
async def test_loader_preserves_complete_large_history_with_one_binding_per_identifier(
    clean_db, async_db_session
):
    originals = [
        _raw({"transaction_id": "HISTORY-0", "fee": "1"}),
        _raw({"transaction_id": "HISTORY-0", "fee": "99"}),
    ]
    async_db_session.add_all(originals)
    await async_db_session.commit()
    history = [
        {"transaction_id": f"HISTORY-{index}", "portfolio_id": "RAW-SOURCE"}
        for index in range(16383)
    ]
    _, selected, _ = await load_transaction_fee_facts(async_db_session, history, lock_sources=True)
    assert [row["id"] for row in selected] == [row.id for row in originals]
    assert [row["payload"]["fee"] for row in selected] == ["1", "99"]


@pytest.mark.asyncio
async def test_exact_loader_rechecks_both_selectors_under_controlled_digest_collision(
    clean_db, async_db_session, monkeypatch
):
    rows = [
        _raw({"transaction_id": "TXN", "fee": "1"}),
        _raw({"transaction_id": "TXN", "fee": "99"}),
        _raw({"transaction_id": "TXN"}, portfolio="FOREIGN"),
        _raw({"transaction_id": "FOREIGN"}),
    ]
    async_db_session.add_all(rows)
    await async_db_session.commit()
    # Inject equal narrowing expressions, not a claim of a native MD5 collision.
    # PostgreSQL executes the actual loader's remaining exact predicates.
    monkeypatch.setattr(
        reprocessing_repository, "func", SimpleNamespace(md5=lambda _: literal("collision"))
    )
    for lock in (False, True):
        _, selected, _ = await load_transaction_fee_facts(
            async_db_session,
            [{"transaction_id": "TXN", "portfolio_id": "RAW-SOURCE"}],
            lock_sources=lock,
        )
        assert [r["id"] for r in selected] == [rows[0].id, rows[1].id]
    _, absent, _ = await load_transaction_fee_facts(
        async_db_session, [{"transaction_id": "ABSENT", "portfolio_id": "RAW-SOURCE"}]
    )
    assert absent == []


@pytest.mark.asyncio
async def test_loader_returns_every_original_in_order_and_excludes_wrong_scope_and_json_shape(
    clean_db,
    async_db_session,
):
    expected = [
        _raw({"transaction_id": "TXN", "fee": "1"}),
        _raw({"transaction_id": "TXN", "fee": "1"}),
        _raw({"transaction_id": "TXN", "fee": "99"}),
    ]
    excluded = [
        _raw({"transaction_id": "TXN"}, portfolio="FOREIGN"),
        _raw({"transaction_id": "TXN"}, family="Other"),
        _raw({"transaction_id": "TXN"}, event_type="Other"),
        _raw({}),
        _raw({"transaction_id": None}),
        _raw({"transaction_id": {"nested": "TXN"}}),
    ]
    numeric = _raw({"transaction_id": 123})
    quoted = _raw({"transaction_id": "TXN'); DROP TABLE outbox_events; --"})
    async_db_session.add_all([*expected, *excluded, numeric, quoted])
    await async_db_session.commit()
    for lock in (False, True):
        fees, raw, receipts = await load_transaction_fee_facts(
            async_db_session,
            [{"transaction_id": "TXN", "portfolio_id": "RAW-SOURCE"}],
            lock_sources=lock,
        )
        assert fees == receipts == []
        assert [dict(row) for row in raw] == [
            {"id": row.id, "aggregate_id": row.aggregate_id, "payload": row.payload}
            for row in expected
        ]
    for identifier, row in (("123", numeric), (quoted.payload["transaction_id"], quoted)):
        _, raw, _ = await load_transaction_fee_facts(
            async_db_session, [{"transaction_id": identifier, "portfolio_id": "RAW-SOURCE"}]
        )
        assert [item["id"] for item in raw] == [row.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["currency", "trade_currency"])
async def test_loaded_valid_original_does_not_bypass_canonical_currency_refusal(
    clean_db,
    async_db_session,
    field,
):
    event = booked_transaction_event(
        transaction_id="CANONICAL-REFUSAL",
        portfolio_id="RAW-SOURCE",
        security_id="RAW-SOURCE-SECURITY",
        transaction_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="25",
        gross_amount="250",
    )
    original = _raw(event.model_dump(mode="json"))
    record = canonical_transaction_record(event)
    async_db_session.add_all(
        [
            portfolio_record(event.portfolio_id),
            instrument_record(
                event.security_id,
                name="Raw source refusal equity",
                isin="SG0000000795",
                currency="USD",
            ),
            record,
            original,
        ]
    )
    await async_db_session.commit()
    await async_db_session.refresh(record)
    # Use the real replay projection, including persisted portfolio-owned tenant authority.
    canonical = dict(
        (await async_db_session.execute(_transactions_to_replay_stmt([event.transaction_id])))
        .mappings()
        .one()
    )
    assert canonical["tenant_id"] == event.tenant_id
    fees, sources, receipts = await load_transaction_fee_facts(async_db_session, [canonical])
    assert len(sources) == 1 and sources[0]["id"] == original.id
    assert qualify_transaction_fee_source(canonical, fees, sources, receipts)[
        "trade_fee"
    ] == Decimal(0)
    canonical.pop(field)
    # Later malformed raw evidence must not mask the earlier canonical-model refusal.
    with pytest.raises(ValidationError):
        qualify_transaction_fee_source(canonical, fees, [*sources, {"aggregate_id": "foreign"}])
    assert (await async_db_session.get(OutboxEvent, original.id)).payload == event.model_dump(
        mode="json"
    )


@pytest.mark.asyncio
async def test_locked_loader_blocks_original_source_writer_until_reader_transaction_ends(
    clean_db,
    async_db_session,
):
    row = _raw({"transaction_id": "LOCKED", "fee": "1"})
    async_db_session.add(row)
    await async_db_session.commit()
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    writer_started = asyncio.Event()
    writer_pid = []

    async def write_original():
        async with factory() as writer:
            writer_pid.append(await writer.scalar(text("SELECT pg_backend_pid()")))
            writer_started.set()
            await writer.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == row.id)
                .values(payload={"transaction_id": "LOCKED", "fee": "99"})
            )
            await writer.commit()

    async with factory() as reader:
        _, raw, _ = await load_transaction_fee_facts(
            reader,
            [{"transaction_id": "LOCKED", "portfolio_id": "RAW-SOURCE"}],
            lock_sources=True,
        )
        assert raw[0]["payload"]["fee"] == "1"
        holder_pid = await reader.scalar(text("SELECT pg_backend_pid()"))
        task = asyncio.create_task(write_original())
        try:
            await asyncio.wait_for(writer_started.wait(), 5)
            async with factory() as observer:
                for _ in range(100):
                    blockers = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": writer_pid[0]}
                    )
                    if holder_pid in blockers:
                        break
                    await asyncio.sleep(0.02)
                assert holder_pid in blockers and not task.done()
            await reader.rollback()
            await asyncio.wait_for(task, 5)
            _, after, _ = await load_transaction_fee_facts(
                reader, [{"transaction_id": "LOCKED", "portfolio_id": "RAW-SOURCE"}]
            )
            assert after[0]["payload"]["fee"] == "99"
        finally:
            await reader.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
