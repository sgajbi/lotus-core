"""Real-PostgreSQL apply/rollback proof for valuation-job hot-path indexes."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

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
