"""Bound valuation claim and stale-recovery hot paths.

Revision ID: c160b2c3d527
Revises: c159b2c3d526
Create Date: 2026-08-22
"""

from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa

from alembic import op

revision: str = "c160b2c3d527"
down_revision: str | Sequence[str] | None = "c159b2c3d526"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_INDEX = "ix_portfolio_valuation_jobs_processing_lease_recovery"
_OLD_INDEX = "ix_portfolio_valuation_jobs_processing_lease_expiry"
_TABLE_NAME = "portfolio_valuation_jobs"
_PROCESSING_PREDICATE = sa.text("status = 'PROCESSING'")


@dataclass(frozen=True)
class _IndexState:
    valid: bool
    ready: bool
    definition: str


def _index_state(index_name: str) -> _IndexState | None:
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
            {"table_name": _TABLE_NAME, "index_name": index_name},
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


def _matches_governed_definition(state: _IndexState, columns: Sequence[str]) -> bool:
    normalized_definition = " ".join(state.definition.lower().split())
    expected_suffix = (
        f"using btree ({', '.join(columns)}) where ((status)::text = 'processing'::text)"
    )
    return normalized_definition.startswith("create index ") and normalized_definition.endswith(
        expected_suffix
    )


def _create_index(index_name: str, columns: Sequence[str]) -> None:
    op.create_index(
        index_name,
        _TABLE_NAME,
        list(columns),
        postgresql_where=_PROCESSING_PREDICATE,
        postgresql_concurrently=True,
        if_not_exists=True,
    )


def _drop_index(index_name: str) -> None:
    op.drop_index(
        index_name,
        table_name=_TABLE_NAME,
        postgresql_concurrently=True,
        if_exists=True,
    )


def _ensure_index(index_name: str, columns: Sequence[str]) -> None:
    state = _index_state(index_name)
    if state is not None and (not state.valid or not state.ready):
        _drop_index(index_name)
        state = None
    if state is not None:
        if not _matches_governed_definition(state, columns):
            raise RuntimeError(
                f"existing {index_name} does not match the governed index definition"
            )
        return
    _create_index(index_name, columns)


def _replace_index(
    *,
    required_name: str,
    required_columns: Sequence[str],
    superseded_name: str,
    superseded_columns: Sequence[str],
) -> None:
    context = op.get_context()
    with context.autocommit_block():
        if context.as_sql:
            _create_index(required_name, required_columns)
            _drop_index(superseded_name)
            return
        _ensure_index(required_name, required_columns)
        superseded_state = _index_state(superseded_name)
        if superseded_state is not None:
            if (
                superseded_state.valid
                and superseded_state.ready
                and not _matches_governed_definition(superseded_state, superseded_columns)
            ):
                raise RuntimeError(
                    f"existing {superseded_name} does not match the governed index definition"
                )
            _drop_index(superseded_name)


def upgrade() -> None:
    """Replace the expiry-only index with deterministic recovery ordering."""

    _replace_index(
        required_name=_NEW_INDEX,
        required_columns=("valuation_lease_expires_at", "id"),
        superseded_name=_OLD_INDEX,
        superseded_columns=("valuation_lease_expires_at",),
    )


def downgrade() -> None:
    """Restore the prior expiry-only partial index."""

    _replace_index(
        required_name=_OLD_INDEX,
        required_columns=("valuation_lease_expires_at",),
        superseded_name=_NEW_INDEX,
        superseded_columns=("valuation_lease_expires_at", "id"),
    )
