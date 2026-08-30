"""PostgreSQL proof for the fail-closed portfolio tenant cutover."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c165b2c3d52c_fix_require_portfolio_tenant.py"
)

PORTFOLIO_INSERT = text(
    """
    INSERT INTO portfolios (
        portfolio_id,
        tenant_id,
        legal_book_id,
        base_currency,
        open_date,
        risk_exposure,
        investment_time_horizon,
        portfolio_type,
        booking_center_code,
        client_id,
        is_leverage_allowed,
        status
    ) VALUES (
        :portfolio_id,
        :tenant_id,
        :legal_book_id,
        'USD',
        DATE '2026-01-01',
        'balanced',
        'long_term',
        'discretionary',
        'SG_BOOKING',
        'CLIENT-001',
        FALSE,
        'active'
    )
    """
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def test_portfolio_tenant_cutover_rejects_ambiguous_rows_then_applies_and_rolls_back(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        if any(
            index["name"] == "ix_portfolios_tenant_portfolio_id"
            for index in inspect(connection).get_indexes("portfolios")
        ):
            migration["downgrade"]()
        connection.execute(
            PORTFOLIO_INSERT,
            {
                "portfolio_id": "TENANT-CUTOVER-AMBIGUOUS",
                "tenant_id": None,
                "legal_book_id": None,
            },
        )

        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError) as exc_info:
            migration["upgrade"]()
        savepoint.rollback()
        error_text = str(exc_info.value)
        assert "portfolio tenant cutover found 1 ambiguous root row" in error_text
        assert "TENANT-CUTOVER-AMBIGUOUS" in error_text

        connection.execute(
            text(
                """
                UPDATE portfolios
                SET tenant_id = 'tenant-test', legal_book_id = 'book-test'
                WHERE portfolio_id = 'TENANT-CUTOVER-AMBIGUOUS'
                """
            )
        )
        migration["upgrade"]()

        columns = {
            column["name"]: column for column in inspect(connection).get_columns("portfolios")
        }
        assert columns["tenant_id"]["nullable"] is False
        assert str(columns["tenant_id"]["type"]) == "VARCHAR(128)"
        assert any(
            index["name"] == "ix_portfolios_tenant_portfolio_id"
            and index["column_names"] == ["tenant_id", "portfolio_id"]
            for index in inspect(connection).get_indexes("portfolios")
        )

        connection.execute(
            PORTFOLIO_INSERT,
            {
                "portfolio_id": "TENANT-CUTOVER-NO-BOOK",
                "tenant_id": "tenant-test",
                "legal_book_id": None,
            },
        )
        invalid_savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                PORTFOLIO_INSERT,
                {
                    "portfolio_id": "TENANT-CUTOVER-NULL",
                    "tenant_id": None,
                    "legal_book_id": None,
                },
            )
        invalid_savepoint.rollback()

        connection.execute(
            text(
                """
                UPDATE portfolios
                SET legal_book_id = 'book-test'
                WHERE portfolio_id = 'TENANT-CUTOVER-NO-BOOK'
                """
            )
        )
        migration["downgrade"]()
        downgraded_columns = {
            column["name"]: column for column in inspect(connection).get_columns("portfolios")
        }
        assert downgraded_columns["tenant_id"]["nullable"] is True
