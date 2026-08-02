"""PostgreSQL apply/rollback proof for lot amortized-cost source authority."""

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
    / "c140b2c3d50d_feat_add_lot_amortized_cost_authority.py"
)

AUTHORITY_INSERT = text(
    """
    INSERT INTO lot_amortized_cost_authority (
        authority_type, tenant_id, legal_book_id, portfolio_id, security_id, lot_id,
        valid_from, valid_to, lifecycle_status, source_version, source_system,
        source_record_id, source_revision, observed_at, authority_content_hash,
        authority_payload
    ) VALUES (
        :authority_type, :tenant_id, :legal_book_id, :portfolio_id, :security_id, :lot_id,
        DATE '2026-01-01', :valid_to, :lifecycle_status, :source_version, :source_system,
        :source_record_id, :source_revision, TIMESTAMPTZ '2026-01-01 08:00:00+00',
        :authority_content_hash, CAST(:authority_payload AS JSONB)
    )
    """
)

PROFILE_EVIDENCE_INSERT = text(
    """
    INSERT INTO lot_amortized_cost_profiles (
        profile_id, profile_version, tenant_id, legal_book_id, portfolio_id,
        security_id, lot_id, effective_date, status, policy_id, policy_version,
        schedule_version, currency, direction, initial_amortized_cost_local,
        redemption_value_local, final_amortized_cost_local, residual_local,
        authority_content_hash, source_references, calculation_lineage,
        profile_content_hash
    ) VALUES (
        'lot-amortized-cost:migration-json-evidence', 1, 'TENANT_SG', 'BOOK_SG_PB',
        'AMORT_PORTFOLIO', 'AMORT_BOND_001', 'AMORT_LOT_001', DATE '2026-01-01',
        'ACTIVE', 'IFRS9_EIR_LOCAL', 1, 1, 'SGD', 'DISCOUNT_ACCRETION',
        97, 100, 100, 0, :authority_hash,
        CAST(:source_references AS JSON), CAST(:calculation_lineage AS JSON),
        :profile_hash
    )
    """
)


def test_authority_migration_applies_enforces_rolls_back_and_reapplies(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    with db_engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        migration["upgrade"].__globals__["op"] = operations
        migration["downgrade"].__globals__["op"] = operations
        if inspect(connection).has_table("lot_amortized_cost_authority"):
            migration["downgrade"]()
        _ensure_predecessor_constraints(connection, operations)
        _seed_source_lot(connection)
        connection.execute(
            PROFILE_EVIDENCE_INSERT,
            {
                "authority_hash": "c" * 64,
                "calculation_lineage": ('{"algorithm_id":"test","algorithm_id":"test"}'),
                "profile_hash": "d" * 64,
                "source_references": ('[{"source_system":"test","source_system":"test"}]'),
            },
        )

        migration["upgrade"]()
        inspector = inspect(connection)
        assert inspector.has_table("lot_amortized_cost_authority")
        profile_columns = {
            column["name"]: column
            for column in inspector.get_columns("lot_amortized_cost_profiles")
        }
        assert str(profile_columns["source_references"]["type"]) == "JSONB"
        assert str(profile_columns["calculation_lineage"]["type"]) == "JSONB"
        canonical_profile_evidence = connection.execute(
            text(
                "SELECT source_references::text, calculation_lineage::text "
                "FROM lot_amortized_cost_profiles "
                "WHERE profile_id = 'lot-amortized-cost:migration-json-evidence'"
            )
        ).one()
        assert canonical_profile_evidence == (
            '[{"source_system": "test"}]',
            '{"algorithm_id": "test"}',
        )
        assert {
            "ix_lot_amort_authority_scope_effective",
            "ix_lot_amort_authority_source_history",
        } <= {index["name"] for index in inspector.get_indexes("lot_amortized_cost_authority")}
        valid = _valid_authority()
        connection.execute(AUTHORITY_INSERT, valid)

        invalid_rows = [
            {"authority_type": "UNSUPPORTED", "source_version": 2},
            {"tenant_id": " TENANT_SG ", "source_version": 2},
            {"valid_to": "2025-12-31", "source_version": 2},
            {"lifecycle_status": "DELETED", "source_version": 2},
            {"source_version": 0},
            {"source_system": " source ", "source_version": 2},
            {"authority_content_hash": "not-a-hash", "source_version": 2},
            {"authority_payload": "[]", "source_version": 2},
            {"lot_id": "WRONG_LOT", "source_version": 2},
        ]
        for overrides in invalid_rows:
            savepoint = connection.begin_nested()
            with pytest.raises(DatabaseError):
                connection.execute(AUTHORITY_INSERT, valid | overrides)
            savepoint.rollback()

        duplicate = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(AUTHORITY_INSERT, valid)
        duplicate.rollback()

        duplicate_member = valid | {
            "authority_content_hash": "b" * 64,
            "authority_payload": '{"currency":"SGD","currency":"SGD"}',
            "source_record_id": "basis-duplicate-member",
            "source_version": 2,
        }
        connection.execute(AUTHORITY_INSERT, duplicate_member)
        canonical_payload = connection.scalar(
            text(
                "SELECT authority_payload::text "
                "FROM lot_amortized_cost_authority "
                "WHERE source_record_id = 'basis-duplicate-member'"
            )
        )
        assert canonical_payload == '{"currency": "SGD"}'

        migration["downgrade"]()
        assert not inspect(connection).has_table("lot_amortized_cost_authority")
        downgraded_columns = {
            column["name"]: column
            for column in inspect(connection).get_columns("lot_amortized_cost_profiles")
        }
        assert str(downgraded_columns["source_references"]["type"]) == "JSON"
        assert str(downgraded_columns["calculation_lineage"]["type"]) == "JSON"
        migration["upgrade"]()
        assert inspect(connection).has_table("lot_amortized_cost_authority")
        reapplied_columns = {
            column["name"]: column
            for column in inspect(connection).get_columns("lot_amortized_cost_profiles")
        }
        assert str(reapplied_columns["source_references"]["type"]) == "JSONB"
        assert str(reapplied_columns["calculation_lineage"]["type"]) == "JSONB"


def _ensure_predecessor_constraints(connection, operations: Operations) -> None:
    for table_name, constraint_name, columns in (
        (
            "portfolios",
            "uq_portfolios_book_scope_identity",
            ["tenant_id", "legal_book_id", "portfolio_id"],
        ),
        (
            "position_lot_state",
            "uq_position_lot_scope_identity",
            ["lot_id", "portfolio_id", "security_id"],
        ),
    ):
        names = {item["name"] for item in inspect(connection).get_unique_constraints(table_name)}
        if constraint_name not in names:
            operations.create_unique_constraint(
                constraint_name,
                table_name,
                columns,
            )


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
            INSERT INTO instruments (security_id, name, isin, currency, product_type)
            VALUES ('AMORT_BOND_001', 'Test Bond', 'XS000AMORT001', 'SGD', 'BOND')
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


def _valid_authority() -> dict[str, object]:
    return {
        "authority_type": "CLEAN_COST_BASIS",
        "tenant_id": "TENANT_SG",
        "legal_book_id": "BOOK_SG_PB",
        "portfolio_id": "AMORT_PORTFOLIO",
        "security_id": "AMORT_BOND_001",
        "lot_id": "AMORT_LOT_001",
        "valid_to": None,
        "lifecycle_status": "ACTIVE",
        "source_version": 1,
        "source_system": "source",
        "source_record_id": "basis-1",
        "source_revision": "revision-1",
        "authority_content_hash": "a" * 64,
        "authority_payload": '{"currency":"SGD"}',
    }
