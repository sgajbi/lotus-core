"""Execute supplier-lineage upgrade in an owned namespace, never downgrade installed source."""

import runpy
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests.test_support.db_cleanup import (
    authorize_database_cleanup,
    require_database_cleanup_authorization,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]


@pytest.fixture
def supplier_migration_namespace(db_engine, clean_db):
    from tests import conftest as native_harness

    authorization = authorize_database_cleanup(
        runtime=native_harness._test_runtime, engine=db_engine
    )
    schema, marker = "core1004_c186_" + uuid4().hex, "core1004-owned:" + uuid4().hex
    require_database_cleanup_authorization(authorization, engine=db_engine)
    with db_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}" AUTHORIZATION CURRENT_USER'))
        connection.execute(text(f"COMMENT ON SCHEMA \"{schema}\" IS '{marker}'"))
    owned = db_engine, authorization, schema, marker
    try:
        yield owned
    finally:
        with _owned_connection(owned) as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@contextmanager
def _owned_connection(owned):
    engine, authorization, schema, marker = owned
    require_database_cleanup_authorization(authorization, engine=engine)
    with engine.begin() as connection:
        identity = connection.execute(
            text("""
            SELECT current_database(), session_user, pg_get_userbyid(nspowner),
                   obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname=:schema
        """),
            {"schema": schema},
        ).one()
        assert tuple(identity) == (
            authorization.target.database,
            authorization.target.username,
            authorization.target.username,
            marker,
        )
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", pg_temp'))
        assert connection.scalar(text("SELECT current_schema()")) == schema
        yield connection


@pytest.mark.parametrize("retained", [None, "transaction", "job"])
def test_actual_supplier_lineage_legacy_upgrade_empty_roundtrip_and_populated_refusal(
    supplier_migration_namespace,
    retained,
):
    migration = runpy.run_path(
        str(Path("alembic/versions/c186b2c3d547_transaction_supplier_lineage.py"))
    )
    with _owned_connection(supplier_migration_namespace) as connection:
        connection.execute(
            text("CREATE TABLE transactions (transaction_id text PRIMARY KEY, source_system text)")
        )
        connection.execute(text("CREATE TABLE ingestion_jobs (job_id text PRIMARY KEY)"))
        connection.execute(text("INSERT INTO transactions VALUES ('legacy', 'CUSTODY')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
            assert tuple(
                connection.execute(
                    text(
                        "SELECT source_record_id, source_batch_id, observed_at FROM transactions "
                        "WHERE transaction_id='legacy'"
                    )
                ).one()
            ) == (None, None, None)
            if retained == "transaction":
                connection.execute(
                    text(
                        "INSERT INTO transactions(transaction_id, source_system, "
                        "source_record_id, source_batch_id) "
                        "VALUES ('retained', 'CUSTODY', 'RECORD-1', 'BATCH-1')"
                    )
                )
            elif retained == "job":
                connection.execute(
                    text(
                        "INSERT INTO ingestion_jobs(job_id, transaction_batch_lineage) "
                        "VALUES ('retained', CAST(:lineage AS json))"
                    ),
                    {
                        "lineage": (
                            '{"source_system":null,"source_batch_id":null,'
                            '"reason":"LEGACY_UNKNOWN"}'
                        )
                    },
                )
            if retained is not None:
                with pytest.raises(RuntimeError, match="downgrade would destroy source evidence"):
                    migration["downgrade"]()
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM pg_trigger "
                            "WHERE tgname='transactions_supplier_lineage_immutable' "
                            "AND tgrelid='transactions'::regclass"
                        )
                    )
                    == 1
                )
                table = "transactions" if retained == "transaction" else "ingestion_jobs"
                key = "transaction_id" if retained == "transaction" else "job_id"
                connection.execute(text(f"DELETE FROM {table} WHERE {key}='retained'"))
            migration["downgrade"]()
            assert connection.scalar(text("SELECT transaction_id FROM transactions")) == "legacy"
            migration["upgrade"]()
            assert connection.scalar(text("SELECT source_batch_id FROM transactions")) is None
