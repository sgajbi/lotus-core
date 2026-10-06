"""Owned source-confirmation DB proof; native adapters, explicit broker substitute.

Requires an authorized isolated candidate-migrated test runtime. Collection or
unit proof is never PostgreSQL acceptance; no canonical runtime is admissible.
"""

import asyncio
import hashlib
import importlib.util
import json
import os
import runpy
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from time import time
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.command_authorization import (
    SOURCE_CORRECTION_CAPABILITY,
    load_command_authorization_policy,
)
from portfolio_common.database_models import (
    IngestionJob,
    OutboxEvent,
    Portfolio,
    Transaction,
    TransactionSourceRevision,
)
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.domain.transaction.payload_identity import (
    transaction_payload_fingerprint,
)
from portfolio_common.enterprise_readiness import (
    _enterprise_auth_context_signature,
    _normalize_headers,
)
from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent
from portfolio_common.event_mapping import transaction_event_v1_payload
from portfolio_common.events import TransactionEvent
from portfolio_common.page_tokens import PageTokenCodec
from portfolio_common.runtime_providers import SystemClock
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.event_replay_service.app import dependencies as status_dependencies
from src.services.event_replay_service.app import main as status_api
from src.services.ingestion_service.app import dependencies
from src.services.ingestion_service.app import main as ingress
from src.services.ingestion_service.app.services import ingestion_job_service
from src.services.persistence_service.app.application.transaction_source_correction import (
    SourceCorrectionRejected,
    TransactionSourceCorrectionApplication,
)
from src.services.persistence_service.app.consumers import base_consumer
from src.services.persistence_service.app.consumers.transaction_source_correction_consumer import (
    TransactionSourceCorrectionConsumer,
)
from src.services.persistence_service.app.repositories import (
    transaction_source_revision_repository as storage,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    build_fx_processed_transaction,
)
from src.services.query_control_plane_service.app.application.transaction_economics.service import (
    TransactionEconomicsService,
)
from src.services.query_control_plane_service.app.contracts.performance_component_economics import (
    PerformanceComponentEconomicsRequest,
)
from src.services.query_control_plane_service.app.infrastructure.transaction_economics_sources import (  # noqa: E501
    SqlAlchemyTransactionEconomicsReader,
)
from src.services.query_service.app.services.transaction_service import (
    TransactionService,
)
from tests.test_support.async_task_coordination import cancel_pending_tasks
from tests.test_support.db_cleanup import (
    authorize_database_cleanup,
    require_database_cleanup_authorization,
)
from tests.test_support.fx_source_evidence import fx_source_fixture
from tests.test_support.transaction_processing import portfolio_record

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

_MIGRATION_PARENT_TABLES = (
    "portfolios",
    "transactions",
    "outbox_events",
    "ingestion_jobs",
)


@pytest.fixture
def source_migration_schema(db_engine, clean_db, source_owned_pg_runtime):
    """Never downgrade the installed schema: own a fresh namespace on the governed DB."""
    from tests import conftest as native_harness

    # An arbitrary external bootstrap is not a governed destructive-DDL capability.
    assert source_owned_pg_runtime is None, "Migration proof requires native owned DB authority"
    authorization = authorize_database_cleanup(
        runtime=native_harness._test_runtime, engine=db_engine
    )
    schema = "core1176_c177_" + uuid4().hex
    marker = "core1176-c177-owned:" + uuid4().hex
    require_database_cleanup_authorization(authorization, engine=db_engine)
    with db_engine.begin() as connection:
        assert connection.scalar(text("SELECT current_database()")) == authorization.target.database
        assert connection.scalar(text("SELECT session_user")) == authorization.target.username
        connection.execute(text(f'CREATE SCHEMA "{schema}" AUTHORIZATION CURRENT_USER'))
        connection.execute(text(f"COMMENT ON SCHEMA \"{schema}\" IS '{marker}'"))
        # Clone parent columns/checks, not c177 SQL or shared data. All inserted values
        # are explicit, so no copied defaults/sequences can write into public.
        for table in _MIGRATION_PARENT_TABLES:
            connection.execute(
                text(f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING CONSTRAINTS)')
            )
        for table, columns in (
            ("portfolios", "tenant_id, portfolio_id"),
            ("outbox_events", "id"),
            ("ingestion_jobs", "tenant_id, job_id"),
        ):
            connection.execute(text(f'ALTER TABLE "{schema}".{table} ADD UNIQUE ({columns})'))
    owned = db_engine, authorization, schema, marker
    try:
        yield owned
    finally:
        # Drop only the exact namespace created here, after revalidating capability
        # and server-side owner/marker. Never clean public or an inherited schema.
        with _source_migration_connection(owned) as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@contextmanager
def _source_migration_connection(owned):
    engine, authorization, schema, marker = owned
    require_database_cleanup_authorization(authorization, engine=engine)
    with engine.begin() as connection:
        identity = connection.execute(
            text("""
                SELECT current_database(), session_user, pg_get_userbyid(nspowner),
                       obj_description(oid, 'pg_namespace')
                FROM pg_namespace WHERE nspname = :schema
            """),
            {"schema": schema},
        ).one()
        assert tuple(identity) == (
            authorization.target.database,
            authorization.target.username,
            authorization.target.username,
            marker,
        ), "Owned migration schema identity changed"
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", pg_temp'))
        assert connection.scalar(text("SELECT current_schema()")) == schema
        yield connection


def _source_migration(connection):
    path = Path(__file__).resolve().parents[4] / "alembic/versions"
    module = runpy.run_path(str(path / "c177b2c3d538_add_transaction_source_evidence_revisions.py"))
    assert module["revision"] == "c177b2c3d538"
    assert module["down_revision"] == "c176b2c3d537"
    # Real Alembic operations, real connection, actual migration implementation.
    module["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
    return module


def _source_migration_shape(connection, schema):
    queries = (
        """SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull
           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           JOIN pg_attribute a ON a.attrelid=c.oid
           WHERE n.nspname=:schema AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
           ORDER BY c.relname, a.attnum""",
        """SELECT c.relname, k.conname, pg_get_constraintdef(k.oid)
           FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema
           ORDER BY c.relname, k.conname""",
        """SELECT tablename, indexname, indexdef FROM pg_indexes
           WHERE schemaname=:schema ORDER BY tablename, indexname""",
        """SELECT c.relname, t.tgname, t.tgtype, t.tgenabled, pg_get_triggerdef(t.oid)
           FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=:schema AND NOT t.tgisinternal ORDER BY c.relname, t.tgname""",
        """SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p
           JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema
           ORDER BY p.proname""",
    )
    return tuple(
        tuple(tuple(row) for row in connection.execute(text(query), {"schema": schema}))
        for query in queries
    )


def _assert_source_migration_installed(connection, schema, module):
    columns, constraints, indexes, triggers, functions = _source_migration_shape(connection, schema)
    assert {row[1] for row in columns if row[0] == "transaction_source_revisions"} == {
        column.name for column in TransactionSourceRevision.__table__.columns
    }
    assert {
        "fk_source_revision_portfolio_owner",
        "fk_source_revision_transaction_owner",
        "fk_source_revision_operation_owner",
        "fk_source_revision_same_chain_predecessor",
        "uq_source_revision_command",
        "uq_source_revision_operation",
        "uq_source_revision_chain_identity",
        "uq_source_revision_child",
        "ck_source_revision_not_self",
        "ck_source_revision_expected_head",
        "ck_source_revision_root_head_hash",
        "ck_source_revision_original_incomplete",
        "ck_source_revision_missing_confirmation_zero",
        "ck_source_revision_local_finite",
        "ck_source_revision_base_finite",
    } <= {row[1] for row in constraints if row[0] == "transaction_source_revisions"}
    assert {
        (row[1], row[2], row[3])
        for row in columns
        if row[0] == "transaction_source_revisions" and row[1] in {"source_local", "source_base"}
    } == {
        ("source_local", "numeric(18,10)", True),
        ("source_base", "numeric(18,10)", True),
    }
    for table in ("portfolios", "transactions", "ingestion_jobs", "outbox_events"):
        assert any(
            row[0] == "transaction_source_revisions"
            and "FOREIGN KEY" in row[2]
            and f"REFERENCES {table}(" in row[2]
            for row in constraints
        )
    assert any(row[1] == "uq_transaction_source_revision_owner" for row in constraints)
    assert any(row[1] == "uq_source_revision_initial" and "WHERE" in row[2] for row in indexes)
    assert len(triggers) == 1
    assert triggers[0][:4] == (
        "transaction_source_revisions",
        "transaction_source_revision_immutable",
        27,
        "O",
    )
    assert "reject_transaction_source_revision_mutation" in triggers[0][4]
    assert len(functions) == 1 and functions[0][0] == "reject_transaction_source_revision_mutation"
    return columns, constraints, indexes, triggers, functions


async def test_actual_c177_empty_upgrade_downgrade_upgrade(source_migration_schema):
    schema = source_migration_schema[2]
    with _source_migration_connection(source_migration_schema) as connection:
        parent = _source_migration_shape(connection, schema)
        module = _source_migration(connection)
        module["upgrade"]()
        installed = _assert_source_migration_installed(connection, schema, module)
    # Every transition commits and is independently reloaded on a new connection.
    with _source_migration_connection(source_migration_schema) as connection:
        assert _source_migration_shape(connection, schema) == installed
        _source_migration(connection)["downgrade"]()
        assert _source_migration_shape(connection, schema) == parent
    with _source_migration_connection(source_migration_schema) as connection:
        assert _source_migration_shape(connection, schema) == parent
        module = _source_migration(connection)
        module["upgrade"]()
        assert _assert_source_migration_installed(connection, schema, module) == installed
    with _source_migration_connection(source_migration_schema) as connection:
        assert _source_migration_shape(connection, schema) == installed


async def test_actual_c177_populated_downgrade_refusal_preserves_authority(
    source_migration_schema, source_confirmation_db
):
    client, factory = source_confirmation_db
    identity = await _seed(factory)
    command, _ = await _submit(client, factory, identity)
    revision = await _execute(factory, command)
    original = await _original_snapshot(factory, identity)
    schema = source_migration_schema[2]
    with _source_migration_connection(source_migration_schema) as connection:
        module = _source_migration(connection)
        module["upgrade"]()
        _assert_source_migration_installed(connection, schema, module)
        # Copy the genuinely committed native UOW fact and its actual parent rows
        # into only this owned schema. No fabricated revision or migration SQL.
        for table, predicate, value in (
            ("portfolios", "portfolio_id", revision.portfolio_id),
            ("transactions", "transaction_id", revision.transaction_id),
            ("outbox_events", "id", revision.root_raw_event_id),
            ("ingestion_jobs", "job_id", revision.operation_id),
            ("transaction_source_revisions", "revision_id", revision.revision_id),
        ):
            connection.execute(
                text(
                    f'INSERT INTO "{schema}".{table} SELECT * FROM public.{table} '
                    f"WHERE {predicate}=:value"
                ),
                {"value": value},
            )
        before = _source_migration_shape(connection, schema)
        facts = _source_migration_rows(connection)
        assert len(facts[-1]) == 1
    with pytest.raises(DBAPIError) as refusal:
        with _source_migration_connection(source_migration_schema) as connection:
            _source_migration(connection)["downgrade"]()
    assert refusal.value.orig.pgcode == "55000"
    assert "Durable source history blocks downgrade" in str(refusal.value.orig)
    with _source_migration_connection(source_migration_schema) as connection:
        assert _source_migration_shape(connection, schema) == before
        assert _source_migration_rows(connection) == facts
    assert await _original_snapshot(factory, identity) == original


def _source_migration_rows(connection):
    return tuple(
        tuple(
            connection.scalars(
                text(f"SELECT to_jsonb(row) FROM {table} row ORDER BY to_jsonb(row)::text")
            )
        )
        for table in (*_MIGRATION_PARENT_TABLES, "transaction_source_revisions")
    )


async def test_actual_c177_upgrade_failure_rolls_back_ddl(source_migration_schema):
    schema = source_migration_schema[2]
    with _source_migration_connection(source_migration_schema) as connection:
        # Deliberate owned-schema conflict makes the actual migration fail after
        # its owner constraint/table/index DDL, without replacing Alembic operations.
        connection.execute(
            text(
                "CREATE FUNCTION reject_transaction_source_revision_mutation() "
                "RETURNS integer LANGUAGE sql AS 'SELECT 1'"
            )
        )
        before = _source_migration_shape(connection, schema)
    with pytest.raises(DBAPIError) as failure:
        with _source_migration_connection(source_migration_schema) as connection:
            _source_migration(connection)["upgrade"]()
    assert failure.value.orig.pgcode == "42723"
    with _source_migration_connection(source_migration_schema) as connection:
        assert _source_migration_shape(connection, schema) == before
        connection.execute(text("DROP FUNCTION reject_transaction_source_revision_mutation()"))
        module = _source_migration(connection)
        module["upgrade"]()
        _assert_source_migration_installed(connection, schema, module)


@pytest.fixture(scope="session")
def source_owned_pg_runtime():
    bootstrap_path = os.getenv("LOTUS_SOURCE_CONFIRMATION_PG_BOOTSTRAP")
    if not bootstrap_path:
        yield None
        return
    spec = importlib.util.spec_from_file_location("source_owned_pg_bootstrap", bootstrap_path)
    assert spec is not None and spec.loader is not None
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    with bootstrap.run(Path(os.environ["LOTUS_REPOSITORY_ROOT"])) as runtime:
        yield runtime


@pytest.fixture(scope="session")
def db_engine(request, source_owned_pg_runtime):
    if source_owned_pg_runtime is None:
        yield request.getfixturevalue("db_engine")
    else:
        yield source_owned_pg_runtime.engine


@pytest.fixture
def clean_db(request, db_engine, source_owned_pg_runtime):
    if source_owned_pg_runtime is None:
        yield request.getfixturevalue("clean_db")
    else:
        source_owned_pg_runtime.clean()
        yield


def _source(companion, *, missing_basis="local", transaction_id=None, producer=None):
    _, prior, _ = fx_source_fixture(None, companion)
    source = replace(
        prior,
        tenant_id="tenant-test",
        realized_fx_pnl_local=None if missing_basis in {"local", "both"} else companion,
        realized_fx_pnl_base=None if missing_basis in {"base", "both"} else companion,
        realized_capital_pnl_local=Decimal(0),
        realized_capital_pnl_base=Decimal(0),
        realized_total_pnl_local=None,
        realized_total_pnl_base=None,
        calculation_lineage=None,
        transaction_id=transaction_id or prior.transaction_id,
    )
    raw = transaction_event_v1_payload(
        TransactionEvent.model_validate(
            {
                name: value
                for name, value in asdict(source).items()
                if name in TransactionEvent.model_fields
            }
        )
    )
    booked = (producer or build_fx_processed_transaction)(source)
    ledger = Transaction(
        **{
            name: value
            for name, value in asdict(booked).items()
            if name in Transaction.__table__.columns and name != "calculation_lineage"
        }
    )
    ledger.calculation_lineage = booked.calculation_lineage.lineage_payload()
    ledger.payload_fingerprint = transaction_payload_fingerprint(raw)
    return raw, ledger


def _headers(
    capability=SOURCE_CORRECTION_CAPABILITY,
    *,
    key="source-proof-key",
    tenant="tenant-test",
):
    headers = {
        "X-Tenant-Id": tenant,
        "X-Actor-Id": "qualified-test-actor",
        "X-Role": "operations",
        "X-Correlation-Id": "qualified-test-correlation",
        "X-Service-Identity": "qualified-test-service",
        "X-Capabilities": capability,
        "X-Enterprise-Auth-Key-Id": "qualified-test-key",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
        "X-Idempotency-Key": key,
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers), "synthetic-http-auth-secret-not-production"
    )
    return headers


@pytest_asyncio.fixture
async def source_confirmation_db(clean_db, async_db_session, monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "qualified-test-key")
    monkeypatch.setenv(
        "ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET",
        "synthetic-http-auth-secret-not-production",
    )
    monkeypatch.setenv(
        "LOTUS_SOURCE_CORRECTION_KEY_TEST",
        "synthetic-purpose-key-material-not-production",
    )
    monkeypatch.setenv(
        "LOTUS_SOURCE_CORRECTION_PRODUCER_ENROLLMENTS",
        json.dumps(
            [
                {
                    "issuer": "qualified-test-issuer",
                    "key_id": "qualified-test-key",
                    "principal": "qualified-test-service",
                    "secret_env": "LOTUS_SOURCE_CORRECTION_KEY_TEST",
                    "signing_enabled": True,
                }
            ]
        ),
    )
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def database_session():
        async with factory() as db:
            yield db

    monkeypatch.setattr(dependencies, "get_async_db_session", database_session)
    monkeypatch.setattr(ingestion_job_service, "get_async_db_session", database_session)
    monkeypatch.setattr(base_consumer, "get_async_db_session", database_session)
    broker = MagicMock()
    broker.flush.return_value = 0
    monkeypatch.setattr(ingress, "get_kafka_producer", lambda: broker)
    transport = httpx.ASGITransport(app=ingress.app)
    async with ingress.app.router.lifespan_context(ingress.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, factory


async def _seed(
    factory,
    companion=Decimal("12"),
    *,
    missing_basis="local",
    transaction_id=None,
    producer=None,
):
    raw, ledger = _source(
        companion,
        missing_basis=missing_basis,
        transaction_id=transaction_id,
        producer=producer,
    )
    async with factory() as db, db.begin():
        if (
            await db.scalar(
                select(Portfolio.id).where(Portfolio.portfolio_id == ledger.portfolio_id)
            )
            is None
        ):
            db.add(portfolio_record(ledger.portfolio_id))
        await db.flush()
        db.add(ledger)
        event = OutboxEvent(
            aggregate_type="RawTransaction",
            aggregate_id=ledger.portfolio_id,
            event_type="RawTransactionPersisted",
            payload=raw,
            topic="transactions.persisted",
            status="PUBLISHED",
            correlation_id="qualified-test-correlation",
            created_at=datetime.now(UTC),
        )
        db.add(event)
        await db.flush()
        identity = str(event.id), canonical_content_hash(raw), ledger.transaction_id
    return identity


def _original_v1_producer():
    fixture = (
        Path(__file__).resolve().parents[3]
        / "fixtures/transaction_source_confirmation/fx_baseline_v1_325d.py"
    )
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == (
        "d460ce07a54069a7e59bcd6dd691aaa98e7f953a156dc1fdfe7679ac233dd671"
    )
    # Relative imports resolve in the original package, not a rewritten historical engine.
    name = (
        "src.services.portfolio_transaction_processing_service.app.domain.transaction.fx."
        "_original_v1_fixture"
    )
    spec = importlib.util.spec_from_file_location(name, fixture)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.FX_BASELINE_CALCULATION_ALGORITHM_VERSION == 1
    return module.build_fx_processed_transaction


async def _read_qcp(factory, *, page_token=None, page_size=1):
    async with factory() as db:
        service = TransactionEconomicsService(
            reader=SqlAlchemyTransactionEconomicsReader(db),
            page_tokens=PageTokenCodec(secret="synthetic-source-consumer-page-secret"),
            clock=SystemClock(),
        )
        response = await service.get_performance_component_economics(
            portfolio_id="QCP-FX-PORT",
            tenant_id=TenantId("tenant-test"),
            request=PerformanceComponentEconomicsRequest(
                as_of_date=date(2026, 4, 1),
                window={"start_date": date(2026, 4, 1), "end_date": date(2026, 4, 1)},
                page={"page_size": page_size, "page_token": page_token},
            ),
        )
        assert await db.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert await db.scalar(text("SHOW transaction_read_only")) == "on"
        return response


async def _read_ledger(
    factory,
    transaction_id,
    *,
    selection="current",
    revision_id=None,
    tenant="tenant-test",
):
    async with factory() as db:
        return await TransactionService(db).get_transaction_record(
            portfolio_id="QCP-FX-PORT",
            transaction_id=transaction_id,
            tenant_context=TenantContext(TenantId(tenant)),
            as_of_date=date(2026, 4, 1),
            source_evidence_selection=selection,
            source_revision_id=revision_id,
        )


@pytest.mark.parametrize("producer_version", [1, 2])
@pytest.mark.parametrize("companion", [Decimal("0"), Decimal("12"), Decimal("-12")])
async def test_actual_pg_source_confirmation_qcp_ledger_cut(
    source_confirmation_db, producer_version, companion
):
    client, factory = source_confirmation_db
    producer = _original_v1_producer() if producer_version == 1 else None
    first = await _seed(factory, companion, transaction_id="SOURCE-A", producer=producer)
    outside = await _seed(factory, companion, transaction_id="SOURCE-Z", producer=producer)
    immutable = await _original_snapshot(factory, outside)
    before = await _read_qcp(factory)
    assert [row.transaction_id for row in before.rows] == [first[2]]
    assert before.rows[0].transaction_source_evidence.status == "INCOMPLETE"
    assert before.rows[0].realized_fx_pnl_local is None
    assert before.page.next_page_token is not None
    original = await _read_ledger(factory, outside[2], selection="original")
    assert (
        original.transaction.transaction_source_evidence.producer_algorithm_version
        == producer_version
    )
    assert original.transaction.realized_fx_pnl_local is None
    assert original.transaction.realized_fx_pnl_base == companion

    command, _ = await _submit(client, factory, outside, key="consumer-cut-confirmation")
    revision = await _execute(factory, command)
    # The changed immutable source lies OUTSIDE the returned page; no financial row changed.
    assert await _original_snapshot(factory, outside) == immutable
    after = await _read_qcp(factory)
    assert after.rows == before.rows
    assert after.source_cut_sha256 != before.source_cut_sha256
    with pytest.raises(ValueError, match="source evidence changed or is unbound"):
        await _read_qcp(factory, page_token=before.page.next_page_token)
    all_rows = await _read_qcp(factory, page_size=10)
    confirmed = next(row for row in all_rows.rows if row.transaction_id == outside[2])
    assert confirmed.transaction_source_evidence.status == "CONFIRMED"
    assert confirmed.transaction_source_evidence.revision_id == revision.revision_id
    assert confirmed.realized_fx_pnl_local == 0
    assert confirmed.realized_fx_pnl_base == companion
    assert (
        confirmed.realized_total_pnl_local
        == confirmed.realized_capital_pnl_local + confirmed.realized_fx_pnl_local
    )
    assert confirmed.realized_total_pnl_base == confirmed.realized_capital_pnl_base + companion
    assert confirmed.transaction_date == date(2026, 4, 1)
    assert confirmed.transaction_source_evidence.confirmed_at > datetime(2026, 4, 1, tzinfo=UTC)

    current = await _read_ledger(factory, outside[2])
    explicit = await _read_ledger(
        factory, outside[2], selection="revision", revision_id=revision.revision_id
    )
    unchanged_original = await _read_ledger(factory, outside[2], selection="original")
    for record in (current, explicit):
        proof = record.transaction.transaction_source_evidence
        assert proof.consumer == "core-ledger" and proof.status == "CONFIRMED"
        assert proof.revision_id == confirmed.transaction_source_evidence.revision_id
        assert proof.revision_sha256 == confirmed.transaction_source_evidence.revision_sha256
        assert record.transaction.realized_fx_pnl_local == 0
        assert record.transaction.realized_fx_pnl_base == companion
        assert record.source_cut_sha256 is not None
    # Serving time is intentionally regenerated; ALL source/financial/proof fields stay identical.
    assert unchanged_original.generated_at >= original.generated_at
    assert unchanged_original.model_dump(exclude={"generated_at"}) == original.model_dump(
        exclude={"generated_at"}
    )
    for target, selected, tenant in (
        (first[2], revision.revision_id, "tenant-test"),
        (outside[2], "not-a-retained-revision", "tenant-test"),
        (outside[2], revision.revision_id, "foreign-tenant"),
    ):
        with pytest.raises(LookupError):
            await _read_ledger(
                factory,
                target,
                selection="revision",
                revision_id=selected,
                tenant=tenant,
            )
    async with factory() as db:
        await db.scalar(select(func.count()).select_from(Transaction))
        with pytest.raises(RuntimeError, match="snapshot"):
            await SqlAlchemyTransactionEconomicsReader(db).establish_performance_read_snapshot()
    async with factory() as db, db.begin():
        raw = await db.get(OutboxEvent, int(outside[0]))
        raw.payload = raw.payload | {"realized_fx_pnl_local": "99"}
    tampered = await _read_qcp(factory, page_size=10)
    unavailable = next(row for row in tampered.rows if row.transaction_id == outside[2])
    assert unavailable.transaction_source_evidence.status == "UNAVAILABLE"
    assert unavailable.realized_fx_pnl_local is None
    assert unavailable.realized_total_pnl_local is None
    assert tampered.source_cut_sha256 != all_rows.source_cut_sha256
    refused = await _read_ledger(factory, outside[2])
    assert refused.transaction.transaction_source_evidence.status == "UNAVAILABLE"
    assert refused.transaction.realized_fx_pnl_local is None
    with pytest.raises(LookupError):
        await _read_ledger(
            factory, outside[2], selection="revision", revision_id=revision.revision_id
        )


async def _submit(client, factory, identity, *, key="source-proof-key", confirmation=None):
    raw_id, raw_hash, target = identity
    response = await client.post(
        f"/ingest/transactions/{target}/source-evidence",
        headers=_headers(key=key),
        json={
            "expected_head_id": raw_id,
            "expected_head_sha256": raw_hash,
            "reason": "Verified source-only missing FX confirmation",
        }
        | ({"realized_pnl_local": "0"} if confirmation is None else confirmation),
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "QUEUED" and response.headers["Location"] == body["status_url"]
    assert body["idempotency"]["key"] != key
    async with factory() as db:
        job = await db.scalar(
            select(IngestionJob).where(IngestionJob.job_id == body["operation_id"])
        )
        assert job.request_payload is None and not job.request_payload_replay_eligible
        intent = await db.scalar(
            select(OutboxEvent).where(
                OutboxEvent.ingestion_job_id == body["operation_id"],
                OutboxEvent.event_type == "TransactionSourceCorrectionRequested",
            )
        )
        return TransactionSourceCorrectionRequestedEvent.model_validate(intent.payload), body


async def _execute(factory, command):
    async with factory() as db, db.begin():
        return await TransactionSourceCorrectionApplication(
            storage.TransactionSourceRevisionRepository(db),
            policy=load_command_authorization_policy(),
        ).execute(command)


async def _original_snapshot(factory, identity):
    async with factory() as db:
        transaction = (
            (
                await db.execute(
                    select(Transaction.__table__).where(Transaction.transaction_id == identity[2])
                )
            )
            .mappings()
            .one()
        )
        raw = (
            (
                await db.execute(
                    select(OutboxEvent.__table__).where(OutboxEvent.id == int(identity[0]))
                )
            )
            .mappings()
            .one()
        )
        return dict(transaction), dict(raw)


@pytest_asyncio.fixture
async def source_status_client(source_confirmation_db, monkeypatch):
    _, factory = source_confirmation_db

    async def database_session():
        async with factory() as db:
            yield db

    monkeypatch.setitem(
        status_api.app.dependency_overrides,
        status_dependencies.get_async_db_session,
        database_session,
    )
    async with status_api.app.router.lifespan_context(status_api.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=status_api.app), base_url="http://test"
        ) as client:
            yield client


class _CapturedIntentMessage:
    """Transport substitute only; native owning consumer/UOW/PG still execute."""

    def __init__(self, command):
        self.command = command

    def value(self):
        return json.dumps(self.command.model_dump(mode="json", exclude_unset=True)).encode()

    def key(self):
        return self.command.authorization.claims.target_transaction_id.encode()

    def headers(self):
        return [("correlation_id", self.command.correlation_id.encode())]

    def topic(self):
        return "transactions.source_correction.commands"

    def partition(self):
        return 0

    def offset(self):
        return 1


async def test_native_consumer_idempotency_uow_has_one_effect(source_confirmation_db):
    client, factory = source_confirmation_db
    command, _ = await _submit(client, factory, await _seed(factory))
    consumer = TransactionSourceCorrectionConsumer(
        bootstrap_servers="explicit-broker-substitute:9092",
        topic="transactions.source_correction.commands",
        group_id="source-confirmation-db-proof",
        dlq_topic=None,
    )
    message = _CapturedIntentMessage(command)
    await consumer.process_message(message)
    await consumer.process_message(message)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(TransactionSourceRevision)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "TransactionSourceEvidenceChanged")
            )
            == 1
        )


@pytest.mark.parametrize("fault", [None, "raw", "output", "retained-receipt"])
async def test_expired_committed_retry_requalifies_actual_retained_pg_cut(
    source_confirmation_db, fault
):
    client, factory = source_confirmation_db
    identity = await _seed(factory)
    command, _ = await _submit(client, factory, identity)
    original = await _execute(factory, command)
    if fault is not None:
        async with factory() as db, db.begin():
            if fault == "raw":
                raw = await db.get(OutboxEvent, int(identity[0]))
                raw.payload = dict(raw.payload) | {"realized_fx_pnl_base": "999"}
            elif fault == "output":
                transaction = await db.scalar(
                    select(Transaction).where(Transaction.transaction_id == original.transaction_id)
                )
                transaction.realized_total_pnl_base = Decimal("999")
            else:
                transaction = await db.scalar(
                    select(Transaction).where(Transaction.transaction_id == original.transaction_id)
                )
                transaction.calculation_lineage = dict(transaction.calculation_lineage) | {
                    "output_content_hash": "0" * 64,
                }
    future = datetime.fromtimestamp(command.authorization.claims.expires_at + 100, UTC)
    async with factory() as db, db.begin():
        application = TransactionSourceCorrectionApplication(
            storage.TransactionSourceRevisionRepository(db),
            policy=load_command_authorization_policy(),
            clock=lambda: future,
        )
        if fault is None:
            retry = await application.execute(command)
            assert retry.revision_id == original.revision_id
        else:
            with pytest.raises(SourceCorrectionRejected, match="FACT_UNVERIFIED"):
                await application.execute(command)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(TransactionSourceRevision)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "TransactionSourceEvidenceChanged")
            )
            == 1
        )


@pytest.mark.parametrize(
    "missing_basis,confirmation,accepted",
    [
        ("base", {"realized_pnl_base": "0"}, True),
        ("both", {"realized_pnl_local": "0", "realized_pnl_base": "0"}, True),
        ("both", {"realized_pnl_local": "0"}, False),
        ("local", {"realized_pnl_local": "1"}, False),
        ("neither", {"realized_pnl_local": "0"}, False),
    ],
)
async def test_actual_pg_currency_basis_confirmation_matrix(
    source_confirmation_db, missing_basis, confirmation, accepted
):
    client, factory = source_confirmation_db
    companion = Decimal("-12") if missing_basis == "base" else Decimal("0")
    identity = await _seed(factory, companion, missing_basis=missing_basis)
    before = await _original_snapshot(factory, identity)
    command, _ = await _submit(client, factory, identity, confirmation=confirmation)
    if accepted:
        revision = await _execute(factory, command)
        assert revision.source_local == (companion if missing_basis == "base" else Decimal("0"))
        assert revision.source_base == 0
        assert revision.original_local_present is (missing_basis == "base")
        assert revision.original_base_present is False
    else:
        with pytest.raises(SourceCorrectionRejected, match="EVIDENCE_REJECTED"):
            await _execute(factory, command)
    assert await _original_snapshot(factory, identity) == before
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(TransactionSourceRevision)) == int(
            accepted
        )
        assert await db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.event_type == "TransactionSourceEvidenceChanged")
        ) == int(accepted)


async def _wait_for_lock(factory, task, pid):
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        if task.done():
            await task
            raise AssertionError("Contender completed without observed PostgreSQL wait")
        async with factory() as observer:
            waiting = await observer.scalar(
                text("""SELECT EXISTS (
                SELECT 1 FROM pg_stat_activity a JOIN pg_locks l ON a.pid=l.pid
                WHERE a.pid=:pid AND a.wait_event_type='Lock' AND NOT l.granted)"""),
                {"pid": pid},
            )
        if waiting:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("No native PostgreSQL lock wait observed")


@pytest.mark.parametrize("companion", [Decimal("0"), Decimal("12"), Decimal("-12")])
async def test_http_intent_real_uow_independent_reload_and_exact_retry(
    source_confirmation_db, companion
):
    client, factory = source_confirmation_db
    identity = await _seed(factory, companion)
    async with factory() as db:
        original = dict(
            (
                await db.execute(
                    select(Transaction.__table__).where(Transaction.transaction_id == identity[2])
                )
            )
            .mappings()
            .one()
        )
    command, accepted = await _submit(client, factory, identity)
    revision = await _execute(factory, command)
    retry = await _execute(factory, command)
    assert retry.revision_id == revision.revision_id
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(TransactionSourceRevision)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "TransactionSourceEvidenceChanged")
            )
            == 1
        )
        current = dict(
            (
                await db.execute(
                    select(Transaction.__table__).where(Transaction.transaction_id == identity[2])
                )
            )
            .mappings()
            .one()
        )
        assert current == original
        persisted = await db.get(TransactionSourceRevision, revision.revision_id)
        assert persisted.source_local == 0 and persisted.source_base == companion
    _, replay_ack = await _submit(client, factory, identity)
    assert replay_ack == accepted


@pytest.mark.parametrize("fault", ["failed", "wrong-entity", "wrong-tenant", "wrong-endpoint"])
async def test_mutable_operation_admission_refuses_without_revision(source_confirmation_db, fault):
    client, factory = source_confirmation_db
    command, _ = await _submit(client, factory, await _seed(factory))
    changes = {
        "failed": {"status": "failed"},
        "wrong-entity": {"entity_type": "transaction"},
        "wrong-tenant": {"tenant_id": "foreign"},
        "wrong-endpoint": {"endpoint": "/ingest/transactions"},
    }[fault]
    async with factory() as db, db.begin():
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == command.authorization.claims.operation_id)
            .values(**changes)
        )
    with pytest.raises(storage.SourceRevisionStorageRejected, match="OPERATION_UNAVAILABLE"):
        await _execute(factory, command)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(TransactionSourceRevision)) == 0


async def test_operation_share_blocks_actual_nonkey_status_update(
    source_confirmation_db,
):
    client, factory = source_confirmation_db
    command, _ = await _submit(client, factory, await _seed(factory))
    operation = command.authorization.claims.operation_id
    task = None
    try:
        async with factory() as holder, holder.begin():
            await storage.TransactionSourceRevisionRepository(holder).lock_admitted_operation(
                tenant_id="tenant-test",
                operation_id=operation,
                command_id=command.authorization.claims.command_id,
            )
            async with factory() as writer:
                pid = await writer.scalar(text("SELECT pg_backend_pid()"))

                async def change_status():
                    await writer.execute(
                        update(IngestionJob)
                        .where(IngestionJob.job_id == operation)
                        .values(status="failed")
                    )
                    await writer.commit()

                task = asyncio.create_task(change_status())
                await _wait_for_lock(factory, task, pid)
                await holder.commit()
                await asyncio.wait_for(task, 8)
        with pytest.raises(storage.SourceRevisionStorageRejected, match="OPERATION_UNAVAILABLE"):
            await _execute(factory, command)
    finally:
        await cancel_pending_tasks(task)


async def test_portfolio_first_overlap_and_stale_cas_have_native_wait(
    source_confirmation_db,
):
    client, factory = source_confirmation_db
    identity = await _seed(factory)
    first, _ = await _submit(client, factory, identity, key="first-command")
    second, _ = await _submit(client, factory, identity, key="second-command")
    task = None
    try:
        async with factory() as holder, holder.begin():
            await holder.execute(
                select(Portfolio)
                .where(Portfolio.portfolio_id == first.portfolio_id)
                .with_for_update()
            )
            async with factory() as contender:
                pid = await contender.scalar(text("SELECT pg_backend_pid()"))

                async def execute_first():
                    result = await TransactionSourceCorrectionApplication(
                        storage.TransactionSourceRevisionRepository(contender),
                        policy=load_command_authorization_policy(),
                    ).execute(first)
                    await contender.commit()
                    return result

                task = asyncio.create_task(execute_first())
                await _wait_for_lock(factory, task, pid)
                await holder.commit()
                await asyncio.wait_for(task, 8)
        with pytest.raises(SourceCorrectionRejected, match="CAS_CONFLICT"):
            await _execute(factory, second)
    finally:
        await cancel_pending_tasks(task)


async def test_failure_after_revision_flush_rolls_back_revision_and_notification(
    source_confirmation_db, monkeypatch
):
    client, factory = source_confirmation_db
    identity = await _seed(factory)
    original = await _original_snapshot(factory, identity)
    command, _ = await _submit(client, factory, identity)
    from portfolio_common.outbox_repository import OutboxRepository

    async def refuse_notification(*args, **kwargs):
        raise RuntimeError("synthetic-notification-failure")

    monkeypatch.setattr(OutboxRepository, "create_outbox_event", refuse_notification)
    with pytest.raises(RuntimeError, match="synthetic-notification-failure"):
        await _execute(factory, command)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(TransactionSourceRevision)) == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "TransactionSourceEvidenceChanged")
            )
            == 0
        )
    assert await _original_snapshot(factory, identity) == original


@pytest.mark.parametrize("mutation", ["update", "delete"])
async def test_migrated_revision_mutation_is_database_refused(source_confirmation_db, mutation):
    client, factory = source_confirmation_db
    command, _ = await _submit(client, factory, await _seed(factory))
    row = await _execute(factory, command)
    async with factory() as db:
        with pytest.raises(DBAPIError) as refusal:
            statement = (
                update(TransactionSourceRevision).values(reason="attempted rewrite")
                if mutation == "update"
                else delete(TransactionSourceRevision)
            )
            await db.execute(
                statement.where(TransactionSourceRevision.revision_id == row.revision_id)
            )
        assert refusal.value.orig.sqlstate == "55000"
        await db.rollback()
        assert (
            await db.get(TransactionSourceRevision, row.revision_id)
        ).reason == command.body.reason


@pytest.mark.parametrize("same_command", [True, False])
async def test_concurrent_command_wait_rechecks_committed_or_cas(
    source_confirmation_db, same_command
):
    client, factory = source_confirmation_db
    identity = await _seed(factory)
    first, _ = await _submit(client, factory, identity, key="first-concurrent-command")
    second = (
        first
        if same_command
        else (await _submit(client, factory, identity, key="second-concurrent-command"))[0]
    )
    task = None
    try:
        async with factory() as holder, holder.begin():
            initial = await TransactionSourceCorrectionApplication(
                storage.TransactionSourceRevisionRepository(holder),
                policy=load_command_authorization_policy(),
            ).execute(first)
            async with factory() as contender:
                pid = await contender.scalar(text("SELECT pg_backend_pid()"))

                async def execute_second():
                    result = await TransactionSourceCorrectionApplication(
                        storage.TransactionSourceRevisionRepository(contender),
                        policy=load_command_authorization_policy(),
                    ).execute(second)
                    await contender.commit()
                    return result

                task = asyncio.create_task(execute_second())
                await _wait_for_lock(factory, task, pid)
                await holder.commit()
                if same_command:
                    result = await asyncio.wait_for(task, 8)
                    assert result.revision_id == initial.revision_id
                else:
                    with pytest.raises(SourceCorrectionRejected, match="CAS_CONFLICT"):
                        await asyncio.wait_for(task, 8)
                    await contender.rollback()
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(TransactionSourceRevision)) == 1
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.event_type == "TransactionSourceEvidenceChanged")
                )
                == 1
            )
    finally:
        await cancel_pending_tasks(task)


@pytest.mark.parametrize("change", [{"tenant_id": "foreign"}, {"status": "failed"}])
async def test_operation_owner_wait_rechecks_actual_admission(source_confirmation_db, change):
    client, factory = source_confirmation_db
    command, _ = await _submit(client, factory, await _seed(factory))
    task = None
    try:
        async with factory() as holder, holder.begin():
            await holder.execute(
                update(IngestionJob)
                .where(IngestionJob.job_id == command.authorization.claims.operation_id)
                .values(**change)
            )
            async with factory() as contender:
                pid = await contender.scalar(text("SELECT pg_backend_pid()"))
                task = asyncio.create_task(
                    TransactionSourceCorrectionApplication(
                        storage.TransactionSourceRevisionRepository(contender),
                        policy=load_command_authorization_policy(),
                    ).execute(command)
                )
                await _wait_for_lock(factory, task, pid)
                await holder.commit()
                with pytest.raises(
                    storage.SourceRevisionStorageRejected, match="OPERATION_UNAVAILABLE"
                ):
                    await asyncio.wait_for(task, 8)
                await contender.rollback()
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(TransactionSourceRevision)) == 0
    finally:
        await cancel_pending_tasks(task)


@pytest.mark.parametrize(
    "fault",
    [None, "intent", "raw", "economic", "operation", "count", "intent-topic", "status"],
)
async def test_public_status_independent_committed_fact_and_refusal(
    source_confirmation_db, source_status_client, fault, monkeypatch
):
    client, factory = source_confirmation_db
    identity = await _seed(factory)
    command, accepted = await _submit(client, factory, identity)
    response = await source_status_client.get(accepted["status_url"], headers=_headers())
    assert response.status_code == 200 and response.json()["status"] == "QUEUED"
    row = await _execute(factory, command)
    if fault is not None:
        async with factory() as db, db.begin():
            if fault == "intent":
                intent = await db.scalar(
                    select(OutboxEvent).where(
                        OutboxEvent.ingestion_job_id == command.authorization.claims.operation_id,
                        OutboxEvent.event_type == "TransactionSourceCorrectionRequested",
                    )
                )
                payload = dict(intent.payload)
                payload["portfolio_id"] = "foreign"
                intent.payload = payload
            elif fault == "raw":
                raw = await db.get(OutboxEvent, int(identity[0]))
                raw.payload = dict(raw.payload) | {"realized_fx_pnl_base": "999"}
            elif fault == "economic":
                await db.execute(
                    update(Transaction)
                    .where(Transaction.transaction_id == identity[2])
                    .values(realized_total_pnl_base=Decimal("999"))
                )
            elif fault == "intent-topic":
                await db.execute(
                    update(OutboxEvent)
                    .where(
                        OutboxEvent.ingestion_job_id == command.authorization.claims.operation_id,
                        OutboxEvent.event_type == "TransactionSourceCorrectionRequested",
                    )
                    .values(topic="foreign.topic")
                )
            else:
                changes = {
                    "operation": {"endpoint": "/ingest/transactions"},
                    "count": {"accepted_count": 2},
                    "status": {"status": "failed"},
                }[fault]
                await db.execute(
                    update(IngestionJob)
                    .where(IngestionJob.job_id == command.authorization.claims.operation_id)
                    .values(**changes)
                )
    response = await source_status_client.get(accepted["status_url"], headers=_headers())
    assert response.status_code == 200
    body = response.json()
    if fault is None:
        assert body["status"] == "SUCCEEDED"
        assert body["revision_id"] == row.revision_id
        assert body["revision_sha256"] == row.revision_sha256
    else:
        assert body["status"] == "UNAVAILABLE"
        assert body["revision_id"] is None and body["revision_sha256"] is None
    assert "qualification_receipt" not in body and "authorization" not in body
    if fault is None:
        foreign = await source_status_client.get(
            accepted["status_url"], headers=_headers(tenant="foreign")
        )
        assert foreign.status_code == 404
        unqualified = await source_status_client.get(
            accepted["status_url"], headers=_headers("ingestion.write")
        )
        assert unqualified.status_code == 403
        forged_headers = _headers()
        forged_headers["X-Tenant-Id"] = "foreign"
        forged = await source_status_client.get(accepted["status_url"], headers=forged_headers)
        assert forged.status_code == 403
        with monkeypatch.context() as invalid_configuration:
            invalid_configuration.setenv("LOTUS_SOURCE_CORRECTION_PRODUCER_ENROLLMENTS", "{")
            unavailable = await source_status_client.get(accepted["status_url"], headers=_headers())
            assert unavailable.status_code == 503
            assert unavailable.json() == {
                "code": "SOURCE_COMMAND_OPERATION_UNAVAILABLE",
                "message": "Source-confirmation operation authority is unavailable.",
                "correlation_id": "qualified-test-correlation",
                "details": {},
            }
