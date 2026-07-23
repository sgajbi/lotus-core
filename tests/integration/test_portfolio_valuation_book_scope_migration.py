"""PostgreSQL apply/rollback proof for portfolio valuation-book authority."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c118b2c3d4f7_feat_add_portfolio_valuation_book_scope.py"
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


def test_portfolio_valuation_book_scope_applies_rolls_back_and_enforces_authority(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        migration["downgrade"]()
        assert "tenant_id" not in {
            column["name"] for column in inspect(connection).get_columns("portfolios")
        }
        assert "legal_book_id" not in {
            column["name"] for column in inspect(connection).get_columns("portfolios")
        }

        migration["upgrade"]()
        columns = {column["name"] for column in inspect(connection).get_columns("portfolios")}
        assert {"tenant_id", "legal_book_id"} <= columns
        checks = {
            constraint["name"]: constraint["sqltext"]
            for constraint in inspect(connection).get_check_constraints("portfolios")
        }
        scope_check = checks["ck_portfolios_valuation_book_scope_complete"]
        # PostgreSQL may render implicit VARCHAR-to-TEXT casts explicitly when
        # reflecting a check constraint. The behavior assertions below remain
        # authoritative; normalize only that dialect-specific representation.
        normalized_scope_check = scope_check.replace("::text", "")
        assert "tenant_id = btrim(tenant_id)" in normalized_scope_check
        assert "legal_book_id = btrim(legal_book_id)" in normalized_scope_check

        for sequence, (tenant_id, legal_book_id) in enumerate(
            [
                ("TENANT-SG", None),
                (None, "PB-SG-01"),
                ("", "PB-SG-01"),
                (" TENANT-SG ", "PB-SG-01"),
            ],
            start=1,
        ):
            savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    PORTFOLIO_INSERT,
                    {
                        "portfolio_id": f"INVALID-{sequence}",
                        "tenant_id": tenant_id,
                        "legal_book_id": legal_book_id,
                    },
                )
            savepoint.rollback()

        connection.execute(
            PORTFOLIO_INSERT,
            {
                "portfolio_id": "LEGACY-UNSCOPED",
                "tenant_id": None,
                "legal_book_id": None,
            },
        )
        connection.execute(
            PORTFOLIO_INSERT,
            {
                "portfolio_id": "AUTHORITATIVE-SCOPED",
                "tenant_id": "TENANT-SG",
                "legal_book_id": "PB-SG-01",
            },
        )
