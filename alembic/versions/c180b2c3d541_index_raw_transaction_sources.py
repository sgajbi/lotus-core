"""Index bounded original raw-transaction source lookup without discarding duplicates.

Revision ID: c180b2c3d541
Revises: c178b2c3d539

The non-unique partial expression index preserves every original source, including
contradictions. Bounded digest keys retain unbounded accepted identifiers; exact
loader comparisons reject collisions. Build and rollback are concurrent; interrupted builds may be
repaired, but a valid same-name index with a different shape is never overwritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c180b2c3d541"
down_revision: str | Sequence[str] | None = "c178b2c3d539"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_outbox_events_raw_transaction_source"
_PREDICATE = "aggregate_type = 'RawTransaction' AND event_type = 'RawTransactionPersisted'"


def _index_state() -> sa.RowMapping | None:
    return (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT source.relname AS table_name, method.amname AS method, "
                "catalog.indnkeyatts AS key_count, catalog.indnatts AS total_count, "
                "catalog.indisunique AS unique, catalog.indisvalid AS valid, "
                "catalog.indisready AS ready, "
                "pg_get_indexdef(index_relation.oid, 1, true) AS key_1, "
                "pg_get_indexdef(index_relation.oid, 2, true) AS key_2, "
                "pg_get_indexdef(index_relation.oid, 3, true) AS key_3, "
                "catalog.indoption::text AS options, "
                "pg_get_expr(catalog.indpred, catalog.indrelid, true) AS predicate "
                "FROM pg_class AS index_relation "
                "JOIN pg_index AS catalog ON catalog.indexrelid = index_relation.oid "
                "JOIN pg_class AS source ON source.oid = catalog.indrelid "
                "JOIN pg_am AS method ON method.oid = index_relation.relam "
                "JOIN pg_namespace AS schema ON schema.oid = index_relation.relnamespace "
                "WHERE schema.nspname = current_schema() "
                "AND index_relation.relname = :index_name"
            ),
            {"index_name": _INDEX},
        )
        .mappings()
        .one_or_none()
    )


def _matches_index(state: sa.RowMapping) -> bool:
    return (
        state["method"] == "btree"
        and state["key_count"] == state["total_count"] == 3
        and not state["unique"]
        and (state["key_1"], state["key_2"], state["key_3"])
        == (
            "md5(aggregate_id::text)",
            "md5(((payload ->> 'transaction_id'::text)::character varying)::text)",
            "id",
        )
        and state["options"] == "0 0 0"
        and state["predicate"]
        == (
            "aggregate_type::text = 'RawTransaction'::text AND "
            "event_type::text = 'RawTransactionPersisted'::text"
        )
    )


def upgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        if not context.as_sql:
            state = _index_state()
            if state is not None:
                if state["table_name"] != "outbox_events":
                    raise RuntimeError(f"existing {_INDEX} belongs to another table")
                if not state["valid"] or not state["ready"]:
                    op.drop_index(_INDEX, table_name="outbox_events", postgresql_concurrently=True)
                elif _matches_index(state):
                    return
                else:
                    raise RuntimeError(f"existing {_INDEX} has an unexpected catalog shape")
        op.create_index(
            _INDEX,
            "outbox_events",
            [
                sa.text("md5(aggregate_id)"),
                sa.text("md5(CAST(payload ->> 'transaction_id' AS VARCHAR))"),
                "id",
            ],
            unique=False,
            postgresql_where=sa.text(_PREDICATE),
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            _INDEX,
            table_name="outbox_events",
            postgresql_concurrently=True,
            if_exists=True,
        )
