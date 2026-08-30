"""Index the portfolio-scoped exact transaction lookup.

Revision ID: c164b2c3d52b
Revises: c163b2c3d52a
Create Date: 2026-08-30
"""

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa

from alembic import op

revision: str = "c164b2c3d52b"
down_revision: str | Sequence[str] | None = "c163b2c3d52a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_transactions_portfolio_transaction_id"
_TABLE_NAME = "transactions"
_INDEX_COLUMNS = ("portfolio_id", "transaction_id")


@dataclass(frozen=True)
class _IndexState:
    valid: bool
    ready: bool
    definition: str


def _index_state() -> _IndexState | None:
    row = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT index_catalog.indisvalid AS valid,
                       index_catalog.indisready AS ready,
                       pg_get_indexdef(index_relation.oid) AS definition
                FROM pg_class AS index_relation
                JOIN pg_index AS index_catalog
                  ON index_catalog.indexrelid = index_relation.oid
                JOIN pg_class AS table_relation
                  ON table_relation.oid = index_catalog.indrelid
                JOIN pg_namespace AS table_schema
                  ON table_schema.oid = table_relation.relnamespace
                WHERE table_schema.nspname = current_schema()
                  AND table_relation.relname = :table_name
                  AND index_relation.relname = :index_name
                """
            ),
            {"table_name": _TABLE_NAME, "index_name": _INDEX_NAME},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    return _IndexState(
        valid=bool(row["valid"]),
        ready=bool(row["ready"]),
        definition=str(row["definition"]),
    )


def _matches_governed_definition(state: _IndexState) -> bool:
    normalized_definition = " ".join(state.definition.lower().split())
    return normalized_definition.startswith("create index ") and normalized_definition.endswith(
        "using btree (portfolio_id, transaction_id)"
    )


def _create_index() -> None:
    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        list(_INDEX_COLUMNS),
        unique=False,
        postgresql_concurrently=True,
        if_not_exists=True,
    )


def _drop_index() -> None:
    op.drop_index(
        _INDEX_NAME,
        table_name=_TABLE_NAME,
        postgresql_concurrently=True,
        if_exists=True,
    )


def _ensure_index() -> None:
    state = _index_state()
    if state is not None and (not state.valid or not state.ready):
        _drop_index()
        state = None
    if state is not None:
        if not _matches_governed_definition(state):
            raise RuntimeError(
                f"existing {_INDEX_NAME} does not match the governed index definition"
            )
        return
    _create_index()


def upgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        if context.as_sql:
            _create_index()
            return
        _ensure_index()


def downgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        if context.as_sql:
            _drop_index()
            return
        state = _index_state()
        if state is None:
            return
        if not _matches_governed_definition(state):
            raise RuntimeError(
                f"existing {_INDEX_NAME} does not match the governed index definition"
            )
        _drop_index()
