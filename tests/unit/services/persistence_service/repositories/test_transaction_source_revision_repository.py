"""Repository UOW/SQL-shape proof only; not PostgreSQL concurrency acceptance."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from operator import setitem
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import (
    IngestionJob,
    OutboxEvent,
    Portfolio,
    Transaction,
    TransactionSourceRevision,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories import (
    transaction_source_revision_repository as storage,
)

SourceRevisionStorageRejected = storage.SourceRevisionStorageRejected
TransactionSourceRevisionRepository = storage.TransactionSourceRevisionRepository


def test_detached_source_snapshot_preserves_all_columns_receipt_lists_and_explicit_zero():
    receipt = {"algorithm_id": "reviewed", "inputs": ["original", {"present": False}]}
    raw_payload = {"transaction_id": "transaction", "nested": {"amount": "0"}}
    transaction = Transaction(
        transaction_id="transaction",
        portfolio_id="portfolio",
        realized_capital_pnl_local=Decimal("0"),
        realized_total_pnl_base=Decimal("-12"),
        payload_fingerprint="fingerprint",
        calculation_lineage=receipt,
    )
    expected = {
        column.name: getattr(transaction, column.name)
        for column in Transaction.__table__.columns
        if column.name not in {"id", "updated_at", "payload_fingerprint", "calculation_lineage"}
    }
    snapshot = storage.retained_source_facts(
        transaction, OutboxEvent(id=7, payload=raw_payload), None
    )
    assert snapshot.transaction.output_material() == expected
    assert snapshot.transaction.receipt_material() == receipt
    assert snapshot.raw_event.payload_material() == raw_payload
    transaction.realized_capital_pnl_local = Decimal("999")
    raw_payload["nested"]["amount"] = "999"
    receipt["inputs"].append("mutated ORM JSON")
    assert snapshot.transaction.output_material() == expected
    assert snapshot.raw_event.payload_material()["nested"]["amount"] == "0"
    assert snapshot.transaction.receipt_material()["inputs"] == ["original", {"present": False}]
    with pytest.raises(TypeError):
        setitem(snapshot.transaction.ledger_output, "realized_capital_pnl_local", Decimal("1"))
    with pytest.raises(FrozenInstanceError):
        setattr(snapshot.transaction, "portfolio_id", "foreign")


def test_revision_projection_preserves_every_column_and_rejects_unknown_schema_field():
    row = TransactionSourceRevision(
        revision_id="revision",
        source_local=Decimal("0"),
        source_base=Decimal("-12"),
        qualification_receipt={"inputs": ["original"]},
        authorization_claims={"tenant_id": "tenant"},
    )
    expected = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    fact = storage.source_revision_fact(row)
    assert fact.material() == expected
    assert set(fact.material()) == set(row.__table__.columns.keys())
    row.source_local = Decimal("999")
    row.qualification_receipt["inputs"].append("mutated ORM JSON")
    assert fact.source_local == Decimal("0")
    assert fact.material()["qualification_receipt"] == {"inputs": ["original"]}
    with pytest.raises(ValueError, match="fact schema"):
        storage.SourceRevisionFact.from_material(expected | {"new_financial_field": Decimal("0")})


@pytest.mark.asyncio
async def test_operation_share_fences_mutable_status_before_canonical_locks():
    db = session()
    job = IngestionJob(
        job_id="operation",
        tenant_id="tenant",
        accepted_count=1,
        endpoint="/ingest/transactions/{transaction_id}/source-evidence",
        entity_type="transaction_source_correction",
        status="accepted",
    )
    intent = OutboxEvent(payload={"authorization": {"claims": {"command_id": "command"}}})
    db.execute.side_effect = [scalar(job), rows([intent])]
    result = await TransactionSourceRevisionRepository(db).lock_admitted_operation(
        tenant_id="tenant", operation_id="operation", command_id="command"
    )
    statement = str(db.execute.await_args_list[0].args[0].compile(dialect=postgresql.dialect()))
    assert statement.endswith("FOR SHARE OF ingestion_jobs")
    assert "ingestion_jobs.tenant_id" in statement and "ingestion_jobs.job_id" in statement
    assert result is not intent and result.payload_material() == intent.payload
    assert len(db.execute.await_args_list) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "failed",
        "foreign-entity",
        "foreign-endpoint",
        "count",
        "missing-intent",
        "duplicate-intent",
    ],
)
async def test_operation_admission_refuses_before_any_target_lock(change):
    db = session()
    job = IngestionJob(
        job_id="operation",
        tenant_id="tenant",
        accepted_count=1,
        endpoint="/ingest/transactions/{transaction_id}/source-evidence",
        entity_type="transaction_source_correction",
        status="queued",
    )
    intents = [OutboxEvent()]
    if change == "failed":
        job.status = "failed"
    elif change == "foreign-entity":
        job.entity_type = "transaction"
    elif change == "foreign-endpoint":
        job.endpoint = "/ingest/transactions"
    elif change == "count":
        job.accepted_count = 2
    elif change == "missing-intent":
        intents = []
    elif change == "duplicate-intent":
        intents *= 2
    db.execute.side_effect = [scalar(None if change == "missing" else job), rows(intents)]
    with pytest.raises(SourceRevisionStorageRejected, match="OPERATION_UNAVAILABLE"):
        await TransactionSourceRevisionRepository(db).lock_admitted_operation(
            tenant_id="tenant", operation_id="operation", command_id="command"
        )
    for call in db.execute.await_args_list:
        assert "FOR UPDATE OF transactions" not in str(
            call.args[0].compile(dialect=postgresql.dialect())
        )


def session():
    db = MagicMock(spec=AsyncSession)
    db.in_transaction.return_value = True
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db


def rows(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_committed_source_cut_is_one_tenant_linked_snapshot_without_effect_locks(missing):
    db = session()
    revision = TransactionSourceRevision(
        revision_id="revision",
        revision_sha256="a" * 64,
        tenant_id="tenant",
        portfolio_id="portfolio",
    )
    transaction = Transaction(transaction_id="transaction", portfolio_id="portfolio")
    raw = OutboxEvent(id=7)
    result = MagicMock()
    result.one_or_none.return_value = None if missing else (transaction, raw, revision)
    db.execute.return_value = result
    repo = TransactionSourceRevisionRepository(db)
    if missing:
        with pytest.raises(SourceRevisionStorageRejected, match="COMMITTED_SOURCE_UNAVAILABLE"):
            await repo.read_committed_source(revision)
    else:
        cut = await repo.read_committed_source(revision)
        assert cut.transaction is not transaction and cut.raw_event is not raw
        assert cut.head.material() == {
            column.name: getattr(revision, column.name) for column in revision.__table__.columns
        }
        assert cut.transaction.portfolio_id == transaction.portfolio_id
        assert cut.raw_event.id == raw.id
    compiled = db.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    statement = str(compiled)
    assert "portfolios.tenant_id" in statement
    assert "transactions.portfolio_id" in statement
    assert "transaction_source_revisions.revision_sha256" in statement
    assert "FOR " not in statement and db.execute.await_count == 1
    assert compiled.params["tenant_id_1"] == "tenant"
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_and_fk_locks_have_explicit_portfolio_transaction_root_head_order():
    db = session()
    transaction = Transaction(transaction_id="transaction", portfolio_id="portfolio")

    async def execute(statement):
        description = statement.column_descriptions[0]
        result = MagicMock()
        if description["entity"] is Transaction:
            result.scalar_one_or_none.return_value = (
                "portfolio" if description["name"] == "portfolio_id" else transaction
            )
            return result
        if description["entity"] is Portfolio:
            result.scalar_one_or_none.return_value = "portfolio"
            return result
        return rows([OutboxEvent(id=7)] if description["entity"] is OutboxEvent else [])

    db.execute.side_effect = execute
    await TransactionSourceRevisionRepository(db).lock_retained_source(
        tenant_id="tenant", transaction_id="transaction"
    )
    locks = [
        str(call.args[0].compile(dialect=postgresql.dialect())).split("FOR ")[-1]
        for call in db.execute.await_args_list
        if "FOR " in str(call.args[0].compile(dialect=postgresql.dialect()))
    ]
    assert locks == [
        "KEY SHARE OF portfolios",
        "UPDATE OF transactions",
        "KEY SHARE OF outbox_events",
        "KEY SHARE OF transaction_source_revisions",
    ]


@pytest.mark.asyncio
async def test_repository_refuses_implicit_autobegin_and_does_not_touch_session():
    db = session()
    db.in_transaction.return_value = False
    repo = TransactionSourceRevisionRepository(db)
    with pytest.raises(SourceRevisionStorageRejected, match="UOW_REQUIRED"):
        await repo.lock_retained_source(tenant_id="tenant", transaction_id="transaction")
    with pytest.raises(SourceRevisionStorageRejected, match="UOW_REQUIRED"):
        await repo.committed_command(tenant_id="tenant", command_id="command")
    with pytest.raises(SourceRevisionStorageRejected, match="UOW_REQUIRED"):
        await repo.stage_revision_and_notification(TransactionSourceRevision())
    db.execute.assert_not_awaited()
    db.flush.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("roots", [[], [OutboxEvent(id=1), OutboxEvent(id=2)]])
async def test_missing_or_duplicate_raw_is_not_reconstructed(roots):
    db = session()
    target = MagicMock()
    target.scalar_one_or_none.return_value = Transaction(
        transaction_id="transaction", portfolio_id="portfolio"
    )
    db.execute.side_effect = [scalar("portfolio"), scalar("portfolio"), target, rows(roots)]
    with pytest.raises(SourceRevisionStorageRejected, match="RAW_AUTHORITY_UNAVAILABLE"):
        await TransactionSourceRevisionRepository(db).lock_retained_source(
            tenant_id="tenant", transaction_id="transaction"
        )
    assert db.execute.await_count == 4
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_owner_lock_and_head_query_use_chain_not_latest_timestamp():
    db = session()
    transaction = Transaction(transaction_id="transaction", portfolio_id="portfolio")
    raw = OutboxEvent(id=7)
    target = MagicMock()
    target.scalar_one_or_none.return_value = transaction
    db.execute.side_effect = [
        scalar("portfolio"),
        scalar("portfolio"),
        target,
        rows([raw]),
        rows([]),
    ]
    retained = await TransactionSourceRevisionRepository(db).lock_retained_source(
        tenant_id="tenant", transaction_id="transaction"
    )
    assert retained.transaction is not transaction and retained.raw_event is not raw
    assert retained.transaction.portfolio_id == transaction.portfolio_id
    assert retained.raw_event.id == raw.id and retained.head is None
    sql = [
        str(call.args[0].compile(dialect=postgresql.dialect()))
        for call in db.execute.await_args_list
    ]
    assert "portfolios.tenant_id" in sql[0] and "FOR " not in sql[0]
    assert "portfolios.tenant_id" in sql[1] and "FOR KEY SHARE OF portfolios" in sql[1]
    assert "portfolios.tenant_id" in sql[2] and "FOR UPDATE OF transactions" in sql[2]
    assert "RawTransactionPersisted" in str(
        db.execute.await_args_list[3]
        .args[0]
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "NOT (EXISTS" in sql[4] and "predecessor_revision_id" in sql[4]
    assert "ORDER BY" not in sql[4]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "results,reason,queries",
    [
        ([scalar(None)], "TARGET_UNAVAILABLE", 1),
        ([scalar("portfolio"), scalar(None)], "TARGET_UNAVAILABLE", 2),
        ([scalar("portfolio"), scalar("portfolio"), scalar(None)], "TARGET_UNAVAILABLE", 3),
        (
            [
                scalar("portfolio"),
                scalar("portfolio"),
                scalar(Transaction(transaction_id="transaction", portfolio_id="changed-owner")),
            ],
            "OWNER_CHANGED",
            3,
        ),
    ],
)
async def test_locked_source_owner_drift_refuses_without_acquiring_later_locks(
    results, reason, queries
):
    db = session()
    db.execute.side_effect = results
    with pytest.raises(SourceRevisionStorageRejected, match=reason):
        await TransactionSourceRevisionRepository(db).lock_retained_source(
            tenant_id="tenant", transaction_id="transaction"
        )
    assert db.execute.await_count == queries
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_staging_adds_only_revision_and_outbox_not_another_transaction():
    db = session()
    revision = TransactionSourceRevision(
        revision_id="revision",
        revision_sha256="1" * 64,
        transaction_id="transaction",
        portfolio_id="portfolio",
        tenant_id="tenant",
        operation_id="operation",
        root_raw_event_id=7,
        correlation_id="qualified-correlation",
        trace_id="qualified-trace",
    )
    fact = storage.source_revision_fact(revision)
    await TransactionSourceRevisionRepository(db).stage_revision_and_notification(fact)
    staged = [call.args[0] for call in db.add.call_args_list]
    assert [type(row) for row in staged] == [TransactionSourceRevision, OutboxEvent]
    assert staged[0] is not fact
    assert {
        column.name: getattr(staged[0], column.name) for column in staged[0].__table__.columns
    } == fact.material()
    assert staged[1].event_type == "TransactionSourceEvidenceChanged"
    assert staged[1].payload["operation_id"] == "operation"
    assert staged[1].payload["revision_sha256"] == "1" * 64
    db.flush.assert_awaited_once()
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_not_called()
