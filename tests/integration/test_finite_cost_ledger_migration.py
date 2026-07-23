"""PostgreSQL lifecycle and enforcement proof for finite cost-ledger values."""

from __future__ import annotations

import runpy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, Numeric, Table, and_, bindparam, cast, select, text, update
from sqlalchemy.exc import DatabaseError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c120b2c3d4f9_fix_enforce_finite_cost_ledger_values.py"
)

NEW_CONSTRAINTS = {
    ("transactions", "ck_transactions_quantity_finite"),
    ("transactions", "ck_transactions_quantity_nonnegative"),
    ("transaction_costs", "ck_transaction_costs_amount_finite"),
    ("position_lot_state", "ck_position_lot_state_numeric_finite"),
    ("position_lot_state", "ck_position_lot_original_quantity_nonnegative"),
    ("position_lot_state", "ck_position_lot_accrued_interest_nonnegative"),
    ("cost_basis_processing_state", "ck_cost_basis_processing_quantity_finite"),
    ("cost_basis_processing_state", "ck_cost_basis_processing_quantity_nonnegative"),
    ("average_cost_pool_state", "ck_average_cost_pool_numeric_finite"),
    ("accrued_income_offset_state", "ck_accrued_income_offset_numeric_finite"),
    ("accrued_income_offset_state", "ck_accrued_income_paid_nonnegative"),
    ("accrued_income_offset_state", "ck_accrued_income_remaining_nonnegative"),
}

GOVERNED_COLUMNS = (
    ("transactions", "quantity", (("transaction_id", "FINITE-TXN-001"),)),
    ("transaction_costs", "amount", (("transaction_id", "FINITE-TXN-001"),)),
    ("position_lot_state", "original_quantity", (("lot_id", "FINITE-LOT-001"),)),
    ("position_lot_state", "open_quantity", (("lot_id", "FINITE-LOT-001"),)),
    ("position_lot_state", "lot_cost_local", (("lot_id", "FINITE-LOT-001"),)),
    ("position_lot_state", "lot_cost_base", (("lot_id", "FINITE-LOT-001"),)),
    (
        "position_lot_state",
        "accrued_interest_paid_local",
        (("lot_id", "FINITE-LOT-001"),),
    ),
    (
        "cost_basis_processing_state",
        "latest_quantity",
        (
            ("portfolio_id", "FINITE-PORT-001"),
            ("security_id", "FINITE-BOND-001"),
        ),
    ),
    (
        "average_cost_pool_state",
        "pool_quantity",
        (
            ("portfolio_id", "FINITE-PORT-001"),
            ("security_id", "FINITE-BOND-001"),
        ),
    ),
    (
        "average_cost_pool_state",
        "pool_cost_local",
        (
            ("portfolio_id", "FINITE-PORT-001"),
            ("security_id", "FINITE-BOND-001"),
        ),
    ),
    (
        "average_cost_pool_state",
        "pool_cost_base",
        (
            ("portfolio_id", "FINITE-PORT-001"),
            ("security_id", "FINITE-BOND-001"),
        ),
    ),
    (
        "accrued_income_offset_state",
        "accrued_interest_paid_local",
        (("offset_id", "FINITE-OFFSET-001"),),
    ),
    (
        "accrued_income_offset_state",
        "remaining_offset_local",
        (("offset_id", "FINITE-OFFSET-001"),),
    ),
)

ROUND_TRIP_COLUMNS = (
    ("transactions", "quantity", (("transaction_id", "FINITE-TXN-001"),)),
    ("transaction_costs", "amount", (("transaction_id", "FINITE-TXN-001"),)),
    ("position_lot_state", "lot_cost_local", (("lot_id", "FINITE-LOT-001"),)),
    (
        "cost_basis_processing_state",
        "latest_quantity",
        (
            ("portfolio_id", "FINITE-PORT-001"),
            ("security_id", "FINITE-BOND-001"),
        ),
    ),
    (
        "average_cost_pool_state",
        "pool_cost_local",
        (
            ("portfolio_id", "FINITE-PORT-001"),
            ("security_id", "FINITE-BOND-001"),
        ),
    ),
    (
        "accrued_income_offset_state",
        "remaining_offset_local",
        (("offset_id", "FINITE-OFFSET-001"),),
    ),
)


def _bind_operations(migration: dict[str, Any], connection) -> Operations:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations
    return operations


def _constraint_names(connection) -> set[tuple[str, str]]:
    rows = connection.execute(
        text(
            """
            SELECT relation.relname, constraint_record.conname
            FROM pg_constraint AS constraint_record
            JOIN pg_class AS relation
              ON relation.oid = constraint_record.conrelid
            JOIN pg_namespace AS namespace_record
              ON namespace_record.oid = relation.relnamespace
            WHERE namespace_record.nspname = current_schema()
              AND constraint_record.contype = 'c'
            """
        )
    )
    return {(table_name, constraint_name) for table_name, constraint_name in rows}


def _normalize_to_previous_revision(connection, operations: Operations) -> None:
    """Drop only c120 checks pre-created by current SQLAlchemy metadata."""

    before = _constraint_names(connection)
    precreated = NEW_CONSTRAINTS & before
    for table_name, constraint_name in sorted(precreated):
        operations.drop_constraint(constraint_name, table_name, type_="check")
    after = _constraint_names(connection)

    assert before - after == precreated
    assert after == before - precreated


def _assert_new_constraint_state(connection, *, present: bool) -> None:
    rows = connection.execute(
        text(
            """
            SELECT relation.relname, constraint_record.conname,
                   constraint_record.convalidated
            FROM pg_constraint AS constraint_record
            JOIN pg_class AS relation
              ON relation.oid = constraint_record.conrelid
            JOIN pg_namespace AS namespace_record
              ON namespace_record.oid = relation.relnamespace
            WHERE namespace_record.nspname = current_schema()
              AND (relation.relname, constraint_record.conname)
                  IN (
                      SELECT *
                      FROM unnest(
                          CAST(:tables AS text[]),
                          CAST(:constraints AS text[])
                      )
                  )
            """
        ),
        {
            "tables": [table_name for table_name, _ in sorted(NEW_CONSTRAINTS)],
            "constraints": [constraint_name for _, constraint_name in sorted(NEW_CONSTRAINTS)],
        },
    ).all()
    found = {
        (table_name, constraint_name): validated for table_name, constraint_name, validated in rows
    }
    if present:
        assert set(found) == NEW_CONSTRAINTS
        assert all(found.values())
    else:
        assert not found


def _seed_valid_cost_ledger(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, base_currency, open_date, risk_exposure,
                investment_time_horizon, portfolio_type, booking_center_code,
                client_id, is_leverage_allowed, status
            ) VALUES (
                'FINITE-PORT-001', 'USD', DATE '2026-07-23', 'balanced',
                'long_term', 'discretionary', 'SG_BOOKING', 'CLIENT-001',
                FALSE, 'active'
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
                trade_currency, currency, transaction_date
            ) VALUES (
                'FINITE-TXN-001', 'FINITE-PORT-001', 'FINITE-BOND-001',
                'FINITE-BOND-001', 'BUY', 10, 100, 1000, 'USD', 'USD',
                TIMESTAMPTZ '2026-07-23 09:00:00+00'
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO transaction_costs (
                transaction_id, fee_type, amount, currency
            ) VALUES ('FINITE-TXN-001', 'BROKERAGE', 1, 'USD')
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
                'FINITE-LOT-001', 'FINITE-TXN-001', 'FINITE-PORT-001',
                'FINITE-BOND-001', 'FINITE-BOND-001', DATE '2026-07-23',
                10, 5, 1000, 1000, 1
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO cost_basis_processing_state (
                portfolio_id, security_id, cost_basis_method,
                latest_transaction_date, latest_dependency_rank,
                latest_cash_dependency_rank, latest_child_sequence,
                latest_target_instrument_id, latest_quantity,
                latest_transaction_id, engine_state_version
            ) VALUES (
                'FINITE-PORT-001', 'FINITE-BOND-001', 'FIFO',
                TIMESTAMPTZ '2026-07-23 09:00:00+00', 0, 0, 0, '', 10,
                'FINITE-TXN-001', 'v1'
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO average_cost_pool_state (
                portfolio_id, security_id, instrument_id,
                representative_source_transaction_id, pool_quantity,
                pool_cost_local, pool_cost_base, state_version
            ) VALUES (
                'FINITE-PORT-001', 'FINITE-BOND-001', 'FINITE-BOND-001',
                'FINITE-TXN-001', 10, 1000, 1000, 'v1'
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO accrued_income_offset_state (
                offset_id, source_transaction_id, portfolio_id, instrument_id,
                security_id, accrued_interest_paid_local, remaining_offset_local
            ) VALUES (
                'FINITE-OFFSET-001', 'FINITE-TXN-001', 'FINITE-PORT-001',
                'FINITE-BOND-001', 'FINITE-BOND-001', 1, 1
            )
            """
        )
    )


def _assert_update_rejected(
    connection,
    *,
    table: Table,
    column_name: str,
    key: tuple[tuple[str, str], ...],
    value: str,
) -> None:
    savepoint = connection.begin_nested()
    with pytest.raises(DatabaseError):
        connection.execute(
            update(table)
            .where(and_(*(table.c[name] == expected for name, expected in key)))
            .values({column_name: cast(bindparam("value"), Numeric())}),
            {"value": value},
        )
    savepoint.rollback()


def _assert_update_accepted(
    connection,
    *,
    table: Table,
    column_name: str,
    key: tuple[tuple[str, str], ...],
    value: str,
) -> None:
    savepoint = connection.begin_nested()
    result = connection.execute(
        update(table)
        .where(and_(*(table.c[name] == expected for name, expected in key)))
        .values({column_name: cast(bindparam("value"), Numeric())}),
        {"value": value},
    )
    assert result.rowcount == 1
    savepoint.rollback()


def _assert_exact_round_trip(
    connection,
    *,
    table: Table,
    column_name: str,
    key: tuple[tuple[str, str], ...],
    value: str,
) -> None:
    savepoint = connection.begin_nested()
    result = connection.execute(
        update(table)
        .where(and_(*(table.c[name] == expected for name, expected in key)))
        .values({column_name: cast(bindparam("value"), Numeric())}),
        {"value": value},
    )
    assert result.rowcount == 1
    persisted = connection.execute(
        select(table.c[column_name]).where(
            and_(*(table.c[name] == expected for name, expected in key))
        )
    ).scalar_one()
    assert persisted == Decimal(value)
    savepoint.rollback()


def test_finite_cost_ledger_migration_lifecycle_and_enforcement(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        operations = _bind_operations(migration, connection)
        _normalize_to_previous_revision(connection, operations)
        _assert_new_constraint_state(connection, present=False)
        _seed_valid_cost_ledger(connection)

        unrelated_before_failed_upgrade = _constraint_names(connection)
        connection.execute(
            text(
                """
                UPDATE transactions
                SET quantity = CAST('NaN' AS NUMERIC)
                WHERE transaction_id = 'FINITE-TXN-001'
                """
            )
        )
        failed_upgrade = connection.begin_nested()
        with pytest.raises(DatabaseError):
            migration["upgrade"]()
        failed_upgrade.rollback()
        _assert_new_constraint_state(connection, present=False)
        assert _constraint_names(connection) == unrelated_before_failed_upgrade
        assert (
            connection.execute(
                text(
                    """
                SELECT CAST(quantity AS TEXT)
                FROM transactions
                WHERE transaction_id = 'FINITE-TXN-001'
                """
                )
            ).scalar_one()
            == "NaN"
        )
        connection.execute(
            text(
                """
                UPDATE transactions
                SET quantity = 10
                WHERE transaction_id = 'FINITE-TXN-001'
                """
            )
        )

        migration["upgrade"]()
        _assert_new_constraint_state(connection, present=True)
        metadata = MetaData()
        metadata.reflect(
            bind=connection,
            only={table_name for table_name, _, _ in GOVERNED_COLUMNS},
        )

        for table_name, column_name, key in GOVERNED_COLUMNS:
            for special_value in ("NaN", "Infinity", "-Infinity"):
                _assert_update_rejected(
                    connection,
                    table=metadata.tables[table_name],
                    column_name=column_name,
                    key=key,
                    value=special_value,
                )
            _assert_update_rejected(
                connection,
                table=metadata.tables[table_name],
                column_name=column_name,
                key=key,
                value="-1",
            )
            if (table_name, column_name) == ("transaction_costs", "amount"):
                _assert_update_rejected(
                    connection,
                    table=metadata.tables[table_name],
                    column_name=column_name,
                    key=key,
                    value="0",
                )

        for table_name, column_name, key in GOVERNED_COLUMNS:
            if (table_name, column_name) == ("transaction_costs", "amount"):
                accepted_values = ("1",)
            elif (table_name, column_name) == (
                "position_lot_state",
                "original_quantity",
            ):
                savepoint = connection.begin_nested()
                result = connection.execute(
                    text(
                        """
                        UPDATE position_lot_state
                        SET original_quantity = 0, open_quantity = 0
                        WHERE lot_id = 'FINITE-LOT-001'
                        """
                    )
                )
                assert result.rowcount == 1
                savepoint.rollback()
                accepted_values = ("10",)
            else:
                accepted_values = ("0", "1")

            for accepted_value in accepted_values:
                _assert_update_accepted(
                    connection,
                    table=metadata.tables[table_name],
                    column_name=column_name,
                    key=key,
                    value=accepted_value,
                )

        for table_name, column_name, key in ROUND_TRIP_COLUMNS:
            for boundary_value in ("0.0000000001", "99999999.9999999999"):
                _assert_exact_round_trip(
                    connection,
                    table=metadata.tables[table_name],
                    column_name=column_name,
                    key=key,
                    value=boundary_value,
                )

        unrelated_before_downgrade = _constraint_names(connection) - NEW_CONSTRAINTS
        migration["downgrade"]()
        _assert_new_constraint_state(connection, present=False)
        assert _constraint_names(connection) == unrelated_before_downgrade

        migration["upgrade"]()
        _assert_new_constraint_state(connection, present=True)
        assert _constraint_names(connection) - NEW_CONSTRAINTS == unrelated_before_downgrade
