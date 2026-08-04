"""PostgreSQL proof for separating legacy book carry from FIFO acquisition basis."""

from __future__ import annotations

import runpy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c144b2c3d511_fix_separate_amortized_book_carry.py"
)


def test_upgrade_restores_fifo_basis_and_downgrade_restores_combined_carry(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        migration["upgrade"].__globals__["op"] = operations
        migration["downgrade"].__globals__["op"] = operations
        if "amortized_book_carrying_local" in {
            column["name"] for column in inspect(connection).get_columns("position_lot_state")
        }:
            migration["downgrade"]()
        _seed_legacy_carry_row(connection)

        migration["upgrade"]()
        separated = connection.execute(
            text(
                "SELECT lot_cost_local, lot_cost_base, "
                "amortized_book_carrying_local, amortized_book_carrying_base "
                "FROM position_lot_state WHERE lot_id = 'AMORT_SEPARATION_LOT'"
            )
        ).one()
        assert tuple(map(Decimal, separated)) == (
            Decimal("3880.0000000000"),
            Decimal("3920.0000000000"),
            Decimal("3980.0000000000"),
            Decimal("4020.0000000000"),
        )

        migration["downgrade"]()
        combined = connection.execute(
            text(
                "SELECT lot_cost_local, lot_cost_base "
                "FROM position_lot_state WHERE lot_id = 'AMORT_SEPARATION_LOT'"
            )
        ).one()
        assert tuple(map(Decimal, combined)) == (
            Decimal("3980.0000000000"),
            Decimal("4020.0000000000"),
        )


@pytest.mark.parametrize(
    ("source_transaction_type", "has_basis_mutation"),
    (("SELL", False), ("BUY", True)),
)
def test_upgrade_fails_closed_without_reconstructible_acquisition_basis(
    db_engine,
    clean_db,
    source_transaction_type: str,
    has_basis_mutation: bool,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        migration["upgrade"].__globals__["op"] = operations
        migration["downgrade"].__globals__["op"] = operations
        if "amortized_book_carrying_local" in {
            column["name"] for column in inspect(connection).get_columns("position_lot_state")
        }:
            migration["downgrade"]()
        _seed_legacy_carry_row(
            connection,
            source_transaction_type=source_transaction_type,
        )
        if has_basis_mutation:
            _seed_basis_mutation(connection)

        with (
            pytest.raises(
                DatabaseError,
                match=(
                    "cannot separate amortized book carry without complete FIFO acquisition basis"
                ),
            ),
            connection.begin_nested(),
        ):
            migration["upgrade"]()


def _seed_legacy_carry_row(connection, *, source_transaction_type: str = "BUY") -> None:
    connection.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                risk_exposure, investment_time_horizon, portfolio_type,
                booking_center_code, client_id, is_leverage_allowed, status
            ) VALUES (
                'AMORT_SEPARATION_PORTFOLIO', 'TENANT_SG', 'BOOK_SG_PB', 'SGD',
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
            VALUES (
                'AMORT_SEPARATION_BOND', 'Carry Separation Bond',
                'XS000SEP0001', 'SGD', 'BOND'
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date, net_cost_local, net_cost
            ) VALUES (
                'AMORT_SEPARATION_BUY', 'AMORT_SEPARATION_PORTFOLIO',
                'AMORT_SEPARATION_BOND', 'AMORT_SEPARATION_BOND',
                :source_transaction_type, 100, 97, 9700, 'SGD', 'SGD',
                TIMESTAMPTZ '2026-01-01 08:00:00+00', 9700, 9800
            )
            """
        ),
        {"source_transaction_type": source_transaction_type},
    )
    connection.execute(
        text(
            """
            INSERT INTO position_lot_state (
                lot_id, source_transaction_id, portfolio_id, instrument_id,
                security_id, acquisition_date, original_quantity, open_quantity,
                lot_cost_local, lot_cost_base, accrued_interest_paid_local
            ) VALUES (
                'AMORT_SEPARATION_LOT', 'AMORT_SEPARATION_BUY',
                'AMORT_SEPARATION_PORTFOLIO', 'AMORT_SEPARATION_BOND',
                'AMORT_SEPARATION_BOND', DATE '2026-01-01', 100, 40, 3980, 4020, 0
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO lot_amortized_cost_profiles (
                profile_id, profile_version, tenant_id, legal_book_id, portfolio_id,
                security_id, lot_id, effective_date, status, policy_id, policy_version,
                schedule_version, currency, direction, initial_amortized_cost_local,
                redemption_value_local, final_amortized_cost_local, residual_local,
                authority_content_hash, source_references, calculation_lineage,
                profile_content_hash
            ) VALUES (
                'lot-amortized-cost:separation', 1, 'TENANT_SG', 'BOOK_SG_PB',
                'AMORT_SEPARATION_PORTFOLIO', 'AMORT_SEPARATION_BOND',
                'AMORT_SEPARATION_LOT', DATE '2026-01-01', 'ACTIVE',
                'IFRS9_EIR_LOCAL', 1, 1, 'SGD', 'DISCOUNT_ACCRETION',
                9700, 10000, 10000, 0, :authority_hash,
                CAST('[{"source_system":"test"}]' AS JSONB),
                CAST('{}' AS JSONB), :profile_hash
            )
            """
        ),
        {"authority_hash": "a" * 64, "profile_hash": "b" * 64},
    )
    connection.execute(
        text(
            """
            UPDATE position_lot_state
            SET amortized_cost_profile_id = 'lot-amortized-cost:separation',
                amortized_cost_profile_version = 1,
                amortized_cost_profile_content_hash = :profile_hash,
                amortized_cost_recognized_through = DATE '2026-06-30',
                amortized_cost_scheduled_local = 9950,
                amortized_cost_book_fx_rate_to_base = 1.0100502513
            WHERE lot_id = 'AMORT_SEPARATION_LOT'
            """
        ),
        {"profile_hash": "b" * 64},
    )


def _seed_basis_mutation(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date
            ) VALUES (
                'AMORT_SEPARATION_DEMERGER', 'AMORT_SEPARATION_PORTFOLIO',
                'AMORT_SEPARATION_BOND', 'AMORT_SEPARATION_BOND',
                'DEMERGER_OUT', 0, 0, 300, 'SGD', 'SGD',
                TIMESTAMPTZ '2026-03-01 08:00:00+00'
            )
            """
        )
    )
