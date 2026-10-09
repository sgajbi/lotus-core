"""Protect concurrent index retry, exact catalog shape, and model/query parity."""

import runpy
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from portfolio_common.database_models import OutboxEvent
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic/versions/c180b2c3d541_index_raw_transaction_sources.py"
)


def _state(**changes):
    return {
        "table_name": "outbox_events",
        "method": "btree",
        "key_count": 3,
        "total_count": 3,
        "unique": False,
        "valid": True,
        "ready": True,
        "key_1": "md5(aggregate_id::text)",
        "key_2": "md5(((payload ->> 'transaction_id'::text)::character varying)::text)",
        "key_3": "id",
        "options": "0 0 0",
        "predicate": (
            "aggregate_type::text = 'RawTransaction'::text AND "
            "event_type::text = 'RawTransactionPersisted'::text"
        ),
    } | changes


def _migration(state, *, offline=False):
    namespace = runpy.run_path(str(MIGRATION))
    operations = MagicMock()
    operations.get_context.return_value.as_sql = offline
    operations.get_context.return_value.autocommit_block.side_effect = nullcontext
    operations.get_bind.return_value.execute.return_value.mappings.return_value.one_or_none.return_value = state  # noqa: E501
    namespace["upgrade"].__globals__["op"] = operations
    return namespace, operations


@pytest.mark.parametrize("state", [None, _state(valid=False), _state(ready=False)])
def test_absent_or_interrupted_owned_index_builds_concurrently(state):
    migration, operations = _migration(state)
    migration["upgrade"]()
    assert operations.drop_index.call_count == (state is not None)
    if state is not None:
        assert operations.drop_index.call_args.kwargs["postgresql_concurrently"] is True
    options = operations.create_index.call_args.kwargs
    assert options["postgresql_concurrently"] is True
    assert options["unique"] is False and options["if_not_exists"] is True
    assert str(options["postgresql_where"]) == migration["_PREDICATE"]


def test_matching_valid_index_is_reused_without_ddl():
    migration, operations = _migration(_state())
    migration["upgrade"]()
    operations.create_index.assert_not_called()
    operations.drop_index.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"table_name": "foreign_table", "valid": False},
        {"method": "hash"},
        {"key_count": 2},
        {"total_count": 4},
        {"unique": True},
        {"key_1": "event_type"},
        {"key_1": "aggregate_id"},
        {"key_2": "payload ->> 'transaction_id'::text"},
        {"key_2": "((payload ->> 'transaction_id'::text)::character varying)"},
        {"key_3": "id DESC"},
        {"options": "0 0 1"},
        {"predicate": None},
        {"predicate": "aggregate_type::text = 'RawTransaction'::text"},
    ],
)
def test_foreign_or_valid_wrong_shape_fails_without_dropping(changes):
    migration, operations = _migration(_state(**changes))
    with pytest.raises(RuntimeError, match="belongs to another table|unexpected catalog shape"):
        migration["upgrade"]()
    operations.drop_index.assert_not_called()
    operations.create_index.assert_not_called()


def test_offline_upgrade_and_downgrade_emit_concurrent_ddl_without_catalog_queries():
    migration, operations = _migration(None, offline=True)
    migration["upgrade"]()
    migration["downgrade"]()
    operations.get_bind.assert_not_called()
    assert operations.create_index.call_args.kwargs["postgresql_concurrently"] is True
    assert operations.drop_index.call_args.kwargs["postgresql_concurrently"] is True
    assert operations.drop_index.call_args.kwargs["if_exists"] is True


def test_model_index_preserves_exact_json_cast_partial_family_and_all_originals():
    index = next(
        item
        for item in OutboxEvent.__table__.indexes
        if item.name == "ix_outbox_events_raw_transaction_source"
    )
    sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert not index.unique
    assert "(md5(aggregate_id), md5(CAST(payload ->> 'transaction_id' AS VARCHAR)), id)" in sql
    assert (
        "WHERE aggregate_type = 'RawTransaction' AND event_type = 'RawTransactionPersisted'" in sql
    )


def test_schema_extraction_preserves_every_preexisting_compiled_index():
    # Golden PostgreSQL DDL from the admitted e765 model, including implicit column indexes.
    definitions = {
        "aggregate_type": "(aggregate_type)",
        "aggregate_id": "(aggregate_id)",
        "status": "(status)",
        "status_created_at": "(status, created_at)",
        "status_last_attempted_at": "(status, last_attempted_at)",
        "status_next_attempt_created_at": "(status, next_attempt_at, created_at)",
        "status_claim_next_attempt_created_at": (
            "(status, claim_expires_at, next_attempt_at, created_at)"
        ),
        "claim_token": "(claim_token)",
        "status_last_failure_at": "(status, last_failure_at)",
        "alternate_lookup_key": "(alternate_lookup_key)",
        "stream_unresolved_order": (
            "(topic, partition_key, created_at, id) WHERE status IN ('PENDING', 'FAILED')"
        ),
    }
    expected = {
        f"ix_outbox_events_{name}": f"CREATE INDEX ix_outbox_events_{name} ON outbox_events {ddl}"
        for name, ddl in definitions.items()
    }
    actual = {
        index.name: str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in OutboxEvent.__table__.indexes
    }
    assert actual.keys() == expected.keys() | {"ix_outbox_events_raw_transaction_source"}
    assert {name: actual[name] for name in expected} == expected
