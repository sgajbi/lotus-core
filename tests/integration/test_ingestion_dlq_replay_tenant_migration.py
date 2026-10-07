"""PostgreSQL proof for consumer-DLQ and replay-audit tenant authority."""

from __future__ import annotations

import runpy
from pathlib import Path

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common import kafka_consumer as kafka_consumer_module
from portfolio_common.db import DatabasePoolMode, create_async_database_engine
from portfolio_common.kafka_consumer import BaseConsumer
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.event_replay_service.app.application.ingestion_operations_queries import (
    IngestionOperationsQueryService,
)
from src.services.event_replay_service.app.dependencies import (
    get_ingestion_operations_query_service,
)
from src.services.event_replay_service.app.main import app as event_replay_app
from src.services.ingestion_service.app.services.infrastructure_errors import (
    InfrastructureAuditWriteFailed,
)
from src.services.ingestion_service.app.services.ingestion_consumer_dlq_events import (
    get_consumer_dlq_event_response,
    list_consumer_dlq_event_responses,
)
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService
from src.services.ingestion_service.app.services.ingestion_replay_audits import (
    get_replay_audit_response,
    list_replay_audit_responses,
    record_consumer_dlq_replay_audit_response,
)
from tests.integration.ingestion_job_sql_fixture import transaction_ingestion_job_insert_fragments
from tests.test_support.portfolio_source_observation_migration_dependencies import (
    downgrade_observation_schema,
    observation_schema_semantics,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.lifecycle]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c176b2c3d537_scope_dlq_replay_audit_tenant.py"
)
SOURCE_REVISION_MIGRATION = MIGRATION.with_name(
    "c177b2c3d538_add_transaction_source_evidence_revisions.py"
)


class _PostgresDlqConsumer(BaseConsumer):
    async def process_message(self, msg) -> None:
        return None


class _ConsumerMessage:
    def topic(self) -> str:
        return "transactions.raw.received"

    def key(self) -> bytes:
        return b"supported-dlq-write"

    def value(self) -> bytes:
        return b'{"transaction_id":"supported-dlq-write"}'


def _bind(migration, connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _restore_predecessor_schema(migration, connection) -> tuple:
    """The managed test stack starts at head; exercise c176 from its real predecessor."""
    observation_semantics = observation_schema_semantics(connection)
    downgrade_observation_schema(connection)
    source_migration = runpy.run_path(str(SOURCE_REVISION_MIGRATION))
    _bind(source_migration, connection)
    # Descend through the real empty-history refusal before dropping its owner key.
    source_migration["downgrade"]()
    _bind(migration, connection)
    migration["downgrade"]()
    assert "tenant_id" not in {
        column["name"] for column in inspect(connection).get_columns("consumer_dlq_events")
    }
    return observation_semantics


def _assert_restored_source_revision_integrity(connection, observation_semantics) -> None:
    assert observation_schema_semantics(connection) == observation_semantics
    owner = next(
        foreign_key
        for foreign_key in inspect(connection).get_foreign_keys(
            "transaction_source_revisions", schema="public"
        )
        if foreign_key["name"] == "fk_source_revision_operation_owner"
    )
    assert owner["constrained_columns"] == ["tenant_id", "operation_id"]
    assert owner["referred_table"] == "ingestion_jobs"
    assert owner["referred_schema"] == "public"
    assert owner["referred_columns"] == ["tenant_id", "job_id"]
    assert owner["options"] == {}
    assert (
        connection.scalar(
            text(
                "SELECT convalidated FROM pg_constraint "
                "WHERE conrelid = 'public.transaction_source_revisions'::regclass "
                "AND conname = 'fk_source_revision_operation_owner' AND contype = 'f'"
            )
        )
        is True
    )
    trigger = connection.execute(
        text(
            """
            SELECT t.tgname, p.proname, pn.nspname, t.tgtype, t.tgenabled,
                   t.tgconstraint
            FROM pg_trigger t
            JOIN pg_proc p ON p.oid = t.tgfoid
            JOIN pg_namespace pn ON pn.oid = p.pronamespace
            WHERE t.tgrelid = 'public.transaction_source_revisions'::regclass
              AND NOT t.tgisinternal
            """
        )
    ).one()
    assert tuple(trigger) == (
        "transaction_source_revision_immutable",
        "reject_transaction_source_revision_mutation",
        "public",
        27,  # BEFORE UPDATE OR DELETE, FOR EACH ROW.
        "O",
        0,
    )


def _insert_job(connection, *, job_id: str, tenant_id: str) -> None:
    columns, values = transaction_ingestion_job_insert_fragments(connection)
    connection.execute(
        text(
            f"""
            INSERT INTO ingestion_jobs (
                job_id, endpoint, entity_type, status, accepted_count,
                correlation_id, request_id, trace_id{columns}
            ) VALUES (
                :job_id, '/ingest/transactions', 'transaction', 'failed', 1,
                :job_id, :job_id, :job_id{values}
            )
            """
        ),
        {"job_id": job_id, "tenant_id": tenant_id},
    )


def _insert_legacy_dlq(connection, *, event_id: str, job_id: str | None) -> None:
    connection.execute(
        text(
            """
            INSERT INTO consumer_dlq_events (
                event_id, original_topic, consumer_group, dlq_topic,
                error_reason_code, error_reason, ingestion_job_id
            ) VALUES (
                :event_id, 'transactions.raw.received', 'persistence-service-group',
                'dlq.persistence_service', 'VALIDATION_ERROR', 'invalid payload', :job_id
            )
            """
        ),
        {"event_id": event_id, "job_id": job_id},
    )


def _insert_legacy_audit(connection, *, replay_id: str, event_id: str, job_id: str | None) -> None:
    connection.execute(
        text(
            """
            INSERT INTO consumer_dlq_replay_audit (
                replay_id, recovery_path, event_id, replay_fingerprint,
                job_id, replay_status, replay_reason
            ) VALUES (
                :replay_id, 'consumer_dlq_replay', :event_id, :replay_id,
                :job_id, 'failed', 'failed'
            )
            """
        ),
        {"replay_id": replay_id, "event_id": event_id, "job_id": job_id},
    )


def test_upgrade_backfills_and_enforces_tenant_scoped_identity(db_engine, clean_db) -> None:
    migration = runpy.run_path(str(MIGRATION))
    with db_engine.begin() as connection:
        head_schema = connection.begin_nested()
        observation_semantics = _restore_predecessor_schema(migration, connection)
        _insert_job(connection, job_id="job-a", tenant_id="tenant-a")
        _insert_job(connection, job_id="job-b", tenant_id="tenant-b")
        _insert_legacy_dlq(connection, event_id="shared-event", job_id="job-a")
        _insert_legacy_audit(
            connection, replay_id="shared-replay", event_id="shared-event", job_id="job-a"
        )
        _insert_legacy_audit(
            connection,
            replay_id="dlq-owned-replay",
            event_id="shared-event",
            job_id=None,
        )

        migration["upgrade"]()
        assert (
            connection.execute(
                text("SELECT tenant_id FROM consumer_dlq_events WHERE event_id='shared-event'")
            ).scalar_one()
            == "tenant-a"
        )
        assert (
            connection.execute(
                text(
                    "SELECT tenant_id FROM consumer_dlq_replay_audit "
                    "WHERE replay_id='dlq-owned-replay'"
                )
            ).scalar_one()
            == "tenant-a"
        )
        assert (
            connection.execute(
                text(
                    "SELECT tenant_id FROM consumer_dlq_replay_audit "
                    "WHERE replay_id='shared-replay'"
                )
            ).scalar_one()
            == "tenant-a"
        )
        dlq_foreign_keys = {
            tuple(foreign_key["constrained_columns"])
            for foreign_key in inspect(connection).get_foreign_keys("consumer_dlq_events")
        }
        audit_foreign_keys = {
            tuple(foreign_key["constrained_columns"])
            for foreign_key in inspect(connection).get_foreign_keys("consumer_dlq_replay_audit")
        }
        assert ("ingestion_job_id",) in dlq_foreign_keys
        assert ("tenant_id", "ingestion_job_id") in dlq_foreign_keys
        assert ("tenant_id", "job_id") in audit_foreign_keys

        connection.execute(
            text(
                """
                INSERT INTO consumer_dlq_events (
                    tenant_id, event_id, original_topic, consumer_group, dlq_topic,
                    error_reason_code, error_reason, ingestion_job_id
                ) VALUES (
                    'tenant-b', 'shared-event', 'transactions.raw.received',
                    'persistence-service-group', 'dlq.persistence_service',
                    'VALIDATION_ERROR', 'invalid payload', 'job-b'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO consumer_dlq_replay_audit (
                    tenant_id, replay_id, recovery_path, event_id, replay_fingerprint,
                    job_id, replay_status, replay_reason
                ) VALUES (
                    'tenant-b', 'shared-replay', 'consumer_dlq_replay', 'shared-event',
                    'tenant-b-fingerprint', 'job-b', 'failed', 'failed'
                )
                """
            )
        )
        connection.execute(
            text(
                "UPDATE consumer_dlq_events SET error_reason='reviewed' "
                "WHERE tenant_id='tenant-b' AND event_id='shared-event'"
            )
        )
        assert (
            connection.execute(
                text(
                    "SELECT error_reason FROM consumer_dlq_events "
                    "WHERE tenant_id='tenant-b' AND event_id='shared-event'"
                )
            ).scalar_one()
            == "reviewed"
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    """
                    INSERT INTO consumer_dlq_events (
                        event_id, original_topic, consumer_group, dlq_topic,
                        error_reason_code, error_reason, ingestion_job_id
                    ) VALUES (
                        'late-writer-event', 'transactions.raw.received',
                        'persistence-service-group', 'dlq.persistence_service',
                        'VALIDATION_ERROR', 'invalid payload', 'job-a'
                    )
                    """
                )
            )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    """
                    INSERT INTO consumer_dlq_replay_audit (
                        replay_id, recovery_path, event_id, replay_fingerprint,
                        job_id, replay_status, replay_reason
                    ) VALUES (
                        'late-writer-replay', 'consumer_dlq_replay', 'shared-event',
                        'late-writer-fingerprint', 'job-a', 'failed', 'failed'
                    )
                    """
                )
            )
        connection.execute(
            text(
                "DELETE FROM consumer_dlq_replay_audit "
                "WHERE tenant_id='tenant-b' AND replay_id='shared-replay'"
            )
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM consumer_dlq_replay_audit "
                    "WHERE tenant_id='tenant-b' AND replay_id='shared-replay'"
                )
            ).scalar_one()
            == 0
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE consumer_dlq_events SET tenant_id='tenant-b' "
                    "WHERE tenant_id='tenant-a' AND event_id='shared-event'"
                )
            )
        with pytest.raises(DBAPIError, match="block downgrade"), connection.begin_nested():
            migration["downgrade"]()
        head_schema.rollback()
        _assert_restored_source_revision_integrity(connection, observation_semantics)


@pytest.mark.parametrize("orphan_kind", ["dlq", "audit", "audit_unknown_job"])
def test_upgrade_refuses_unattributable_legacy_rows(db_engine, clean_db, orphan_kind: str) -> None:
    migration = runpy.run_path(str(MIGRATION))
    with db_engine.begin() as connection:
        head_schema = connection.begin_nested()
        observation_semantics = _restore_predecessor_schema(migration, connection)
        if orphan_kind == "dlq":
            _insert_legacy_dlq(connection, event_id="orphan-event", job_id=None)
        elif orphan_kind == "audit":
            _insert_legacy_audit(
                connection, replay_id="orphan-replay", event_id="missing-event", job_id=None
            )
        else:
            _insert_job(connection, job_id="audit-owner-job", tenant_id="tenant-a")
            _insert_legacy_dlq(connection, event_id="owned-event", job_id="audit-owner-job")
            _insert_legacy_audit(
                connection,
                replay_id="unknown-job-replay",
                event_id="owned-event",
                job_id="missing-job",
            )
        expected_error = (
            "unknown ingestion job" if orphan_kind == "audit_unknown_job" else "unattributable"
        )
        with pytest.raises(DBAPIError, match=expected_error):
            migration["upgrade"]()
        head_schema.rollback()
        _assert_restored_source_revision_integrity(connection, observation_semantics)


def test_upgrade_refuses_conflicting_job_and_dlq_owners(db_engine, clean_db) -> None:
    migration = runpy.run_path(str(MIGRATION))
    with db_engine.begin() as connection:
        head_schema = connection.begin_nested()
        observation_semantics = _restore_predecessor_schema(migration, connection)
        _insert_job(connection, job_id="conflict-job-a", tenant_id="tenant-a")
        _insert_job(connection, job_id="conflict-job-b", tenant_id="tenant-b")
        _insert_legacy_dlq(connection, event_id="conflict-event", job_id="conflict-job-a")
        _insert_legacy_audit(
            connection,
            replay_id="conflict-replay",
            event_id="conflict-event",
            job_id="conflict-job-b",
        )
        with pytest.raises(DBAPIError, match="conflicting owner"):
            migration["upgrade"]()
        head_schema.rollback()
        _assert_restored_source_revision_integrity(connection, observation_semantics)


def test_clean_upgrade_and_downgrade_remain_executable(db_engine, clean_db) -> None:
    migration = runpy.run_path(str(MIGRATION))
    with db_engine.begin() as connection:
        head_schema = connection.begin_nested()
        observation_semantics = _restore_predecessor_schema(migration, connection)
        migration["upgrade"]()
        assert "tenant_id" in {
            column["name"] for column in inspect(connection).get_columns("consumer_dlq_events")
        }
        _insert_job(connection, job_id="downgrade-job", tenant_id="tenant-a")
        connection.execute(
            text(
                """
                INSERT INTO consumer_dlq_events (
                    tenant_id, event_id, original_topic, consumer_group, dlq_topic,
                    error_reason_code, error_reason, ingestion_job_id
                ) VALUES (
                    'tenant-a', 'downgrade-event', 'transactions.raw.received',
                    'persistence-service-group', 'dlq.persistence_service',
                    'VALIDATION_ERROR', 'invalid payload', 'downgrade-job'
                );
                INSERT INTO consumer_dlq_replay_audit (
                    tenant_id, replay_id, recovery_path, event_id, replay_fingerprint,
                    job_id, replay_status, replay_reason
                ) VALUES (
                    'tenant-a', 'downgrade-replay', 'consumer_dlq_replay', 'downgrade-event',
                    'downgrade-fingerprint', 'downgrade-job', 'failed', 'failed'
                )
                """
            )
        )
        migration["downgrade"]()
        dlq_indexes = {
            index["name"]: index for index in inspect(connection).get_indexes("consumer_dlq_events")
        }
        audit_indexes = {
            index["name"]: index
            for index in inspect(connection).get_indexes("consumer_dlq_replay_audit")
        }
        assert dlq_indexes["ix_consumer_dlq_events_event_id"]["unique"] is True
        assert audit_indexes["ix_consumer_dlq_replay_audit_replay_id"]["unique"] is True
        assert (
            connection.execute(
                text("SELECT count(*) FROM consumer_dlq_events WHERE event_id='downgrade-event'")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM consumer_dlq_replay_audit "
                    "WHERE replay_id='downgrade-replay'"
                )
            ).scalar_one()
            == 1
        )
        migration["upgrade"]()
        head_schema.rollback()
        _assert_restored_source_revision_integrity(connection, observation_semantics)


@pytest.mark.asyncio
async def test_real_postgres_reads_hide_foreign_colliding_identities(
    db_engine, clean_db, monkeypatch
) -> None:
    with db_engine.begin() as connection:
        _insert_job(connection, job_id="tenant-read-job-a", tenant_id="tenant-a")
        _insert_job(connection, job_id="tenant-read-job-b", tenant_id="tenant-b")
        for tenant_id, job_id in (
            ("tenant-a", "tenant-read-job-a"),
            ("tenant-b", "tenant-read-job-b"),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO consumer_dlq_events (
                        tenant_id, event_id, original_topic, consumer_group, dlq_topic,
                        error_reason_code, error_reason, ingestion_job_id
                    ) VALUES (
                        :tenant_id, 'colliding-event', 'transactions.raw.received',
                        'persistence-service-group', 'dlq.persistence_service',
                        'VALIDATION_ERROR', 'invalid payload', :job_id
                    );
                    INSERT INTO consumer_dlq_replay_audit (
                        tenant_id, replay_id, recovery_path, event_id, replay_fingerprint,
                        job_id, replay_status, replay_reason
                    ) VALUES (
                        :tenant_id, 'colliding-replay', 'consumer_dlq_replay', 'colliding-event',
                        'colliding-fingerprint', :job_id, 'failed', 'failed'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "job_id": job_id},
            )
        connection.execute(
            text(
                """
                INSERT INTO consumer_dlq_replay_audit (
                    tenant_id, replay_id, recovery_path, event_id, replay_fingerprint,
                    job_id, replay_status, replay_reason
                ) VALUES (
                    'tenant-b', 'tenant-b-only', 'consumer_dlq_replay', 'colliding-event',
                    'tenant-b-only-fingerprint', 'tenant-read-job-b', 'failed', 'failed'
                )
                """
            )
        )

    async_url = db_engine.url.render_as_string(hide_password=False).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
    async_engine = create_async_database_engine(
        runtime_identity="lotus-core-test",
        database_url=async_url,
        pool_mode=DatabasePoolMode.NULL,
    )
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)

    async def session_factory():
        async with sessions() as session:
            yield session

    try:
        monkeypatch.setattr(kafka_consumer_module, "get_async_db_session", session_factory)
        consumer = _PostgresDlqConsumer(
            bootstrap_servers="localhost:9092",
            topic="transactions.raw.received",
            group_id="persistence-service-group",
            dlq_topic="dlq.persistence_service",
        )
        message = _ConsumerMessage()
        redacted_message = consumer._redacted_message_value_text(message)
        await consumer._record_consumer_dlq_event(
            msg=message,
            error=ValueError("invalid payload"),
            error_reason_code="VALIDATION_ERROR",
            correlation_id="corr-supported-write",
            tenant_id="tenant-a",
            redacted_payload_text=redacted_message,
            ingestion_job_id="tenant-read-job-a",
        )
        with db_engine.connect() as connection:
            supported_event_id = connection.execute(
                text(
                    "SELECT event_id FROM consumer_dlq_events "
                    "WHERE tenant_id='tenant-a' AND original_key='supported-dlq-write'"
                )
            ).scalar_one()
        supported_replay_id = await record_consumer_dlq_replay_audit_response(
            tenant_id="tenant-a",
            recovery_path="consumer_dlq_replay",
            event_id=supported_event_id,
            replay_fingerprint="supported-write-fingerprint",
            correlation_id="corr-supported-write",
            job_id="tenant-read-job-a",
            endpoint="/ingest/transactions",
            replay_status="dry_run",
            dry_run=True,
            replay_reason="supported persistence proof",
            requested_by="integration-test",
            session_factory=session_factory,
        )
        with pytest.raises(IntegrityError):
            await consumer._record_consumer_dlq_event(
                msg=message,
                error=ValueError("invalid payload"),
                error_reason_code="VALIDATION_ERROR",
                correlation_id="corr-wrong-tenant",
                tenant_id="tenant-b",
                redacted_payload_text=redacted_message,
                ingestion_job_id="tenant-read-job-a",
            )
        with pytest.raises(InfrastructureAuditWriteFailed):
            await record_consumer_dlq_replay_audit_response(
                tenant_id="tenant-b",
                recovery_path="consumer_dlq_replay",
                event_id=supported_event_id,
                replay_fingerprint="wrong-tenant-fingerprint",
                correlation_id="corr-wrong-tenant",
                job_id="tenant-read-job-a",
                endpoint="/ingest/transactions",
                replay_status="dry_run",
                dry_run=True,
                replay_reason="must fail",
                requested_by="integration-test",
                session_factory=session_factory,
            )
        assert (
            await get_replay_audit_response(
                tenant_id="tenant-a",
                replay_id=supported_replay_id,
                session_factory=session_factory,
            )
            is not None
        )
        tenant_a_events = await list_consumer_dlq_event_responses(
            tenant_id="tenant-a",
            limit=1,
            original_topic=None,
            consumer_group=None,
            session_factory=session_factory,
        )
        tenant_b_audits = await list_replay_audit_responses(
            tenant_id="tenant-b",
            limit=10,
            recovery_path=None,
            replay_status=None,
            replay_fingerprint="colliding-fingerprint",
            job_id=None,
            session_factory=session_factory,
        )
        tenant_a_job_audits = await list_replay_audit_responses(
            tenant_id="tenant-a",
            limit=1,
            recovery_path=None,
            replay_status=None,
            replay_fingerprint=None,
            job_id="tenant-read-job-a",
            session_factory=session_factory,
        )
        assert [(row.event_id, row.ingestion_job_id) for row in tenant_a_events] == [
            (supported_event_id, "tenant-read-job-a")
        ]
        assert [(row.replay_id, row.job_id) for row in tenant_b_audits] == [
            ("colliding-replay", "tenant-read-job-b")
        ]
        assert [(row.replay_id, row.job_id) for row in tenant_a_job_audits] == [
            (supported_replay_id, "tenant-read-job-a")
        ]
        assert (
            await get_consumer_dlq_event_response(
                tenant_id="tenant-a", event_id="colliding-event", session_factory=session_factory
            )
            is not None
        )
        assert (
            await get_replay_audit_response(
                tenant_id="tenant-a", replay_id="tenant-b-only", session_factory=session_factory
            )
            is None
        )

        query_service = IngestionOperationsQueryService(
            ingestion_job_service=IngestionJobService(session_factory=session_factory)
        )
        event_replay_app.dependency_overrides[get_ingestion_operations_query_service] = lambda: (
            query_service
        )
        transport = httpx.ASGITransport(app=event_replay_app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={
                "X-Tenant-Id": "tenant-a",
                "X-Lotus-Ops-Token": "lotus-core-ops-local",
            },
        ) as client:
            events_response = await client.get(
                "/ingestion/dlq/consumer-events", params={"limit": 1}
            )
            audits_response = await client.get(
                "/ingestion/audit/replays",
                params={
                    "limit": 1,
                    "job_id": "tenant-read-job-a",
                    "replay_fingerprint": "colliding-fingerprint",
                },
            )
            direct_response = await client.get("/ingestion/audit/replays/colliding-replay")
            foreign_response = await client.get("/ingestion/audit/replays/tenant-b-only")
        assert events_response.status_code == 200
        assert [row["ingestion_job_id"] for row in events_response.json()["events"]] == [
            "tenant-read-job-a"
        ]
        assert audits_response.status_code == 200
        assert [row["job_id"] for row in audits_response.json()["audits"]] == ["tenant-read-job-a"]
        assert direct_response.status_code == 200
        assert direct_response.json()["job_id"] == "tenant-read-job-a"
        assert foreign_response.status_code == 404
    finally:
        event_replay_app.dependency_overrides.pop(get_ingestion_operations_query_service, None)
        await async_engine.dispose()
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM consumer_dlq_replay_audit "
                    "WHERE tenant_id IN ('tenant-a', 'tenant-b')"
                )
            )
            connection.execute(
                text("DELETE FROM consumer_dlq_events WHERE tenant_id IN ('tenant-a', 'tenant-b')")
            )
            connection.execute(
                text(
                    "DELETE FROM ingestion_jobs "
                    "WHERE job_id IN ('tenant-read-job-a', 'tenant-read-job-b')"
                )
            )
