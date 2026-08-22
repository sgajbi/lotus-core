"""Real-PostgreSQL apply/rollback proof for valuation-job hot-path indexes."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c160b2c3d527_perf_bound_valuation_job_hot_paths.py"
)

NEW_INDEX = "ix_portfolio_valuation_jobs_processing_lease_recovery"
OLD_INDEX = "ix_portfolio_valuation_jobs_processing_lease_expiry"


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _valuation_job_indexes(connection) -> set[str]:
    return {index["name"] for index in inspect(connection).get_indexes("portfolio_valuation_jobs")}


def test_hot_path_index_replacement_applies_and_rolls_back_online(
    db_engine,
    clean_db,
) -> None:
    del clean_db
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.connect() as connection:
        _bind_operations(migration, connection)
        assert NEW_INDEX in _valuation_job_indexes(connection)
        assert OLD_INDEX not in _valuation_job_indexes(connection)
        connection.rollback()

        try:
            migration["downgrade"]()
            assert OLD_INDEX in _valuation_job_indexes(connection)
            assert NEW_INDEX not in _valuation_job_indexes(connection)
            connection.rollback()

            migration["upgrade"]()
            assert NEW_INDEX in _valuation_job_indexes(connection)
            assert OLD_INDEX not in _valuation_job_indexes(connection)
        finally:
            indexes = _valuation_job_indexes(connection)
            connection.rollback()
            if NEW_INDEX not in indexes and OLD_INDEX in indexes:
                migration["upgrade"]()


def test_hot_path_index_upgrade_resumes_after_concurrent_create(
    db_engine,
    clean_db,
) -> None:
    """A retry accepts the governed new index and completes the old-index removal."""

    del clean_db
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.connect() as connection:
        _bind_operations(migration, connection)
        migration["downgrade"]()
        assert OLD_INDEX in _valuation_job_indexes(connection)
        assert NEW_INDEX not in _valuation_job_indexes(connection)
        connection.rollback()

        operations = migration["upgrade"].__globals__["op"]
        with operations.get_context().autocommit_block():
            operations.create_index(
                NEW_INDEX,
                "portfolio_valuation_jobs",
                ["valuation_lease_expires_at", "id"],
                postgresql_where=text("status = 'PROCESSING'"),
                postgresql_concurrently=True,
            )

        try:
            assert {NEW_INDEX, OLD_INDEX}.issubset(_valuation_job_indexes(connection))
            connection.rollback()

            migration["upgrade"]()
            assert NEW_INDEX in _valuation_job_indexes(connection)
            assert OLD_INDEX not in _valuation_job_indexes(connection)
        finally:
            indexes = _valuation_job_indexes(connection)
            connection.rollback()
            if NEW_INDEX not in indexes:
                migration["upgrade"]()
