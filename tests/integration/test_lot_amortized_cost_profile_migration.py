"""PostgreSQL apply/rollback proof for lot amortized-cost profile persistence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError, IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c139b2c3d50c_feat_add_lot_amortized_cost_profiles.py"
)
LATER_MIGRATION = (
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

PROFILE_INSERT = text(
    """
    INSERT INTO lot_amortized_cost_profiles (
        profile_id,
        profile_version,
        tenant_id,
        legal_book_id,
        portfolio_id,
        security_id,
        lot_id,
        effective_date,
        status,
        eligibility_reason,
        policy_id,
        policy_version,
        schedule_version,
        currency,
        direction,
        initial_amortized_cost_local,
        redemption_value_local,
        final_amortized_cost_local,
        residual_local,
        authority_content_hash,
        source_references,
        calculation_lineage,
        profile_content_hash
    ) VALUES (
        'lot-amortized-cost:test',
        :profile_version,
        :tenant_id,
        :legal_book_id,
        :portfolio_id,
        :security_id,
        :lot_id,
        DATE '2026-01-01',
        :status,
        :eligibility_reason,
        :policy_id,
        :policy_version,
        :schedule_version,
        :currency,
        :direction,
        :initial_cost,
        :redemption_value,
        :final_cost,
        :residual,
        :authority_hash,
        CAST(:source_references AS JSON),
        CAST(:calculation_lineage AS JSON),
        :profile_hash
    )
    """
)

PERIOD_INSERT = text(
    """
    INSERT INTO lot_amortized_cost_periods (
        profile_id,
        profile_version,
        period_ordinal,
        period_start_date,
        period_end_date,
        year_fraction,
        period_rate,
        begin_amortized_cost_local,
        interest_income_local,
        cash_coupon_local,
        amortization_amount_local,
        end_amortized_cost_local,
        rounding_adjustment_local,
        calculation_output_hash,
        period_content_hash
    ) VALUES (
        'lot-amortized-cost:test',
        :profile_version,
        :period_ordinal,
        DATE '2026-01-01',
        :period_end_date,
        :year_fraction,
        '0.05',
        '97',
        '5',
        '2',
        '3',
        :end_cost,
        '0',
        :output_hash,
        :period_hash
    )
    """
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _normalize_to_previous_revision(migration: dict[str, Any], connection) -> None:
    inspector = inspect(connection)
    operations = migration["upgrade"].__globals__["op"]
    if inspector.has_table("lot_amortized_cost_periods"):
        operations.drop_table("lot_amortized_cost_periods")
    if inspector.has_table("lot_amortized_cost_profiles"):
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


def _downgrade_later_revisions(connection) -> list[dict[str, Any]]:
    """Remove dependent revisions newest-first before exercising the profile schema."""

    later_migrations: list[dict[str, Any]] = []
    for table_name, marker_column, migration_path in (
        ("position_lot_state", "amortized_cost_profile_id", RESIDUAL_CARRY_MIGRATION),
        ("lot_disposal_allocations", "amortized_cost_profile_id", DISPOSAL_EVIDENCE_MIGRATION),
        ("lot_disposal_receipts", None, HEAD_MIGRATION),
        ("lot_amortized_cost_authority", None, LATER_MIGRATION),
    ):
        inspector = inspect(connection)
        if not inspector.has_table(table_name):
            continue
        if marker_column is not None and marker_column not in {
            column["name"] for column in inspector.get_columns(table_name)
        }:
            continue
        later_migration: dict[str, Any] = runpy.run_path(str(migration_path))
        _bind_operations(later_migration, connection)
        later_migration["downgrade"]()
        later_migrations.append(later_migration)
    return later_migrations


def _seed_source_lot(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                risk_exposure, investment_time_horizon, portfolio_type,
                booking_center_code, client_id, is_leverage_allowed, status
            ) VALUES (
                'AMORT_PORTFOLIO', 'TENANT_SG', 'BOOK_SG_PB', 'SGD',
                DATE '2026-01-01', 'MODERATE', 'LONG_TERM', 'ADVISORY',
                'SG', 'CLIENT_001', FALSE, 'ACTIVE'
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                risk_exposure, investment_time_horizon, portfolio_type,
                booking_center_code, client_id, is_leverage_allowed, status
            ) VALUES (
                'AMORT_PORTFOLIO_ALT', 'TENANT_SG', 'BOOK_SG_PB', 'SGD',
                DATE '2026-01-01', 'MODERATE', 'LONG_TERM', 'ADVISORY',
                'SG', 'CLIENT_002', FALSE, 'ACTIVE'
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO instruments (security_id, name, isin, currency, product_type)
            VALUES ('AMORT_BOND_001', 'Amortization Test Bond', 'XS000AMORT001', 'SGD', 'BOND')
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO instruments (security_id, name, isin, currency, product_type)
            VALUES ('AMORT_BOND_ALT', 'Alternate Test Bond', 'XS000AMORT002', 'SGD', 'BOND')
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date
            ) VALUES (
                'AMORT_BUY_001', 'AMORT_PORTFOLIO', 'AMORT_BOND_001',
                'AMORT_BOND_001', 'BUY', 100, 97, 9700, 'SGD', 'SGD',
                TIMESTAMPTZ '2026-01-01 08:00:00+00'
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO position_lot_state (
                lot_id, source_transaction_id, portfolio_id, instrument_id,
                security_id, acquisition_date, original_quantity, open_quantity,
                lot_cost_local, lot_cost_base, accrued_interest_paid_local
            ) VALUES (
                'AMORT_LOT_001', 'AMORT_BUY_001', 'AMORT_PORTFOLIO',
                'AMORT_BOND_001', 'AMORT_BOND_001', DATE '2026-01-01',
                100, 100, 9700, 9700, 0
            )
            """
        )
    )


def _valid_profile() -> dict[str, object]:
    return {
        "profile_version": 1,
        "tenant_id": "TENANT_SG",
        "legal_book_id": "BOOK_SG_PB",
        "portfolio_id": "AMORT_PORTFOLIO",
        "security_id": "AMORT_BOND_001",
        "lot_id": "AMORT_LOT_001",
        "status": "ACTIVE",
        "eligibility_reason": None,
        "policy_id": "IFRS9_EIR_LOCAL",
        "policy_version": 1,
        "schedule_version": 1,
        "currency": "SGD",
        "direction": "DISCOUNT_ACCRETION",
        "initial_cost": "97",
        "redemption_value": "100",
        "final_cost": "100",
        "residual": "0",
        "authority_hash": "a" * 64,
        "source_references": '[{"source_system":"test"}]',
        "calculation_lineage": "{}",
        "profile_hash": "b" * 64,
    }


def _valid_period() -> dict[str, object]:
    return {
        "profile_version": 1,
        "period_ordinal": 1,
        "period_end_date": "2027-01-01",
        "year_fraction": "1",
        "end_cost": "100",
        "output_hash": "c" * 64,
        "period_hash": "d" * 64,
    }


def test_lot_amortized_cost_profiles_apply_roll_back_and_enforce_ledgers(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        later_migrations = _downgrade_later_revisions(connection)
        _bind_operations(migration, connection)
        _normalize_to_previous_revision(migration, connection)
        migration["upgrade"]()
        inspector = inspect(connection)
        assert inspector.has_table("lot_amortized_cost_profiles")
        assert inspector.has_table("lot_amortized_cost_periods")
        assert "ix_lot_amort_profile_scope_version" in {
            index["name"] for index in inspector.get_indexes("lot_amortized_cost_profiles")
        }
        assert "ix_lot_amort_period_profile_end" in {
            index["name"] for index in inspector.get_indexes("lot_amortized_cost_periods")
        }
        _seed_source_lot(connection)
        profile = _valid_profile()
        connection.execute(PROFILE_INSERT, profile)
        connection.execute(PERIOD_INSERT, _valid_period())

        invalid_profiles = [
            {"tenant_id": " TENANT_SG ", "profile_version": 2},
            {"tenant_id": "TENANT_ALT", "profile_version": 2},
            {"legal_book_id": "BOOK_ALT", "profile_version": 2},
            {"portfolio_id": "AMORT_PORTFOLIO_ALT", "profile_version": 2},
            {"security_id": "AMORT_BOND_ALT", "profile_version": 2},
            {"profile_version": 0},
            {"profile_version": 2, "status": "DELETED"},
            {"profile_version": 2, "currency": "sgd"},
            {"profile_version": 2, "initial_cost": "-1"},
            {"profile_version": 2, "initial_cost": "NaN"},
            {"profile_version": 2, "authority_hash": "not-a-hash"},
            {"profile_version": 2, "source_references": "{}"},
            {
                "profile_version": 2,
                "status": "PARKED",
                "eligibility_reason": None,
            },
        ]
        for overrides in invalid_profiles:
            savepoint = connection.begin_nested()
            with pytest.raises(DatabaseError):
                connection.execute(PROFILE_INSERT, profile | overrides)
            savepoint.rollback()

        duplicate = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(PROFILE_INSERT, profile)
        duplicate.rollback()

        invalid_periods = [
            {"period_ordinal": 0},
            {"period_ordinal": 2, "period_end_date": "2025-12-31"},
            {"period_ordinal": 2, "year_fraction": "0"},
            {"period_ordinal": 2, "end_cost": "-1"},
            {"period_ordinal": 2, "end_cost": "Infinity"},
            {"period_ordinal": 2, "period_hash": "not-a-hash"},
            {"profile_version": 999},
        ]
        period = _valid_period()
        for overrides in invalid_periods:
            savepoint = connection.begin_nested()
            with pytest.raises(DatabaseError):
                connection.execute(PERIOD_INSERT, period | overrides)
            savepoint.rollback()

        migration["downgrade"]()
        assert not inspect(connection).has_table("lot_amortized_cost_periods")
        assert not inspect(connection).has_table("lot_amortized_cost_profiles")

        migration["upgrade"]()
        assert inspect(connection).has_table("lot_amortized_cost_profiles")
        assert inspect(connection).has_table("lot_amortized_cost_periods")
        for later_migration in reversed(later_migrations):
            later_migration["upgrade"]()
        if later_migrations:
            assert inspect(connection).has_table("lot_amortized_cost_authority")
        if any(migration["revision"] == "c141b2c3d50e" for migration in later_migrations):
            assert inspect(connection).has_table("lot_disposal_receipts")
            assert inspect(connection).has_table("lot_disposal_allocations")
        if any(migration["revision"] == "c142b2c3d50f" for migration in later_migrations):
            assert "amortized_cost_profile_id" in {
                column["name"]
                for column in inspect(connection).get_columns("lot_disposal_allocations")
            }
        if any(migration["revision"] == "c143b2c3d510" for migration in later_migrations):
            assert "amortized_cost_profile_id" in {
                column["name"] for column in inspect(connection).get_columns("position_lot_state")
            }
