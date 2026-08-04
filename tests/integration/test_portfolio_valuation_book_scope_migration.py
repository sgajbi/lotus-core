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
DEPENDENT_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c139b2c3d50c_feat_add_lot_amortized_cost_profiles.py"
)
LATEST_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c140b2c3d50d_feat_add_lot_amortized_cost_authority.py"
)
HEAD_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c141b2c3d50e_feat_add_lot_disposal_receipts.py"
)
DISPOSAL_EVIDENCE_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c142b2c3d50f_feat_add_amortized_disposal_evidence.py"
)
RESIDUAL_CARRY_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c143b2c3d510_fix_conserve_amortized_cost_residual.py"
)
BASIS_TRANSFER_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c146b2c3d513_feat_add_lot_basis_transfer_receipts.py"
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


def _downgrade_dependent_schema(connection) -> list[dict[str, Any]]:
    """Downgrade later schema that deliberately references valuation-book scope."""

    dependent_migrations: list[dict[str, Any]] = []
    inspector = inspect(connection)
    if inspector.has_table("lot_basis_transfer_allocations"):
        basis_transfer_migration: dict[str, Any] = runpy.run_path(str(BASIS_TRANSFER_MIGRATION))
        _bind_operations(basis_transfer_migration, connection)
        basis_transfer_migration["downgrade"]()
        dependent_migrations.append(basis_transfer_migration)
        inspector = inspect(connection)
    residual_columns = {column["name"] for column in inspector.get_columns("position_lot_state")}
    if "amortized_cost_profile_id" in residual_columns:
        residual_migration: dict[str, Any] = runpy.run_path(str(RESIDUAL_CARRY_MIGRATION))
        _bind_operations(residual_migration, connection)
        residual_migration["downgrade"]()
        dependent_migrations.append(residual_migration)
        inspector = inspect(connection)
    disposal_evidence_columns = {
        column["name"] for column in inspector.get_columns("lot_disposal_allocations")
    }
    if "amortized_cost_profile_id" in disposal_evidence_columns:
        disposal_evidence_migration: dict[str, Any] = runpy.run_path(
            str(DISPOSAL_EVIDENCE_MIGRATION)
        )
        _bind_operations(disposal_evidence_migration, connection)
        disposal_evidence_migration["downgrade"]()
        dependent_migrations.append(disposal_evidence_migration)
        inspector = inspect(connection)
    if inspector.has_table("lot_disposal_receipts"):
        head_migration: dict[str, Any] = runpy.run_path(str(HEAD_MIGRATION))
        _bind_operations(head_migration, connection)
        head_migration["downgrade"]()
        dependent_migrations.append(head_migration)
        inspector = inspect(connection)
    if inspector.has_table("lot_amortized_cost_authority"):
        latest_migration: dict[str, Any] = runpy.run_path(str(LATEST_MIGRATION))
        _bind_operations(latest_migration, connection)
        latest_migration["downgrade"]()
        dependent_migrations.append(latest_migration)
        inspector = inspect(connection)
    if not inspector.has_table("lot_amortized_cost_profiles"):
        return dependent_migrations
    dependent_migration: dict[str, Any] = runpy.run_path(str(DEPENDENT_MIGRATION))
    _bind_operations(dependent_migration, connection)
    operations = dependent_migration["downgrade"].__globals__["op"]
    if inspector.has_table("lot_amortized_cost_periods"):
        operations.drop_table("lot_amortized_cost_periods")
    operations.drop_table("lot_amortized_cost_profiles")
    for table_name, constraint_name in (
        ("position_lot_state", "uq_position_lot_scope_identity"),
        ("portfolios", "uq_portfolios_book_scope_identity"),
    ):
        unique_constraints = {
            constraint["name"]
            for constraint in inspect(connection).get_unique_constraints(table_name)
        }
        if constraint_name in unique_constraints:
            operations.drop_constraint(constraint_name, table_name, type_="unique")
    dependent_migrations.append(dependent_migration)
    return dependent_migrations


def test_portfolio_valuation_book_scope_applies_rolls_back_and_enforces_authority(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        dependent_migrations = _downgrade_dependent_schema(connection)
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

        for dependent_migration in reversed(dependent_migrations):
            dependent_migration["upgrade"]()
        if dependent_migrations:
            inspector = inspect(connection)
            assert inspector.has_table("lot_amortized_cost_profiles")
            assert inspector.has_table("lot_amortized_cost_periods")
            if any(migration["revision"] == "c140b2c3d50d" for migration in dependent_migrations):
                assert inspector.has_table("lot_amortized_cost_authority")
            if any(migration["revision"] == "c141b2c3d50e" for migration in dependent_migrations):
                assert inspector.has_table("lot_disposal_receipts")
                assert inspector.has_table("lot_disposal_allocations")
            if any(migration["revision"] == "c142b2c3d50f" for migration in dependent_migrations):
                assert "amortized_cost_profile_id" in {
                    column["name"] for column in inspector.get_columns("lot_disposal_allocations")
                }
            if any(migration["revision"] == "c143b2c3d510" for migration in dependent_migrations):
                assert "amortized_cost_profile_id" in {
                    column["name"] for column in inspector.get_columns("position_lot_state")
                }
            if any(migration["revision"] == "c146b2c3d513" for migration in dependent_migrations):
                assert inspector.has_table("lot_basis_transfer_receipts")
                assert inspector.has_table("lot_basis_transfer_allocations")
