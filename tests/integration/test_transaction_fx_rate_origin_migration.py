"""PostgreSQL proof for durable transaction FX-rate provenance."""

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
    / "c175b2c3d536_add_transaction_fx_rate_origin.py"
)


def test_fx_rate_origin_backfill_constraint_and_rollback(db_engine, clean_db) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    with db_engine.connect() as connection:
        operations = Operations(MigrationContext.configure(connection))
        migration["upgrade"].__globals__["op"] = operations
        migration["downgrade"].__globals__["op"] = operations
        migration["downgrade"]()
        connection.execute(
            text(
                """
                INSERT INTO portfolios (
                    portfolio_id, tenant_id, legal_book_id, base_currency, open_date, risk_exposure,
                    investment_time_horizon, portfolio_type, booking_center_code,
                    client_id, is_leverage_allowed, status
                ) VALUES (
                    'FX_ORIGIN_PORT', 'tenant-test', 'BOOK_SG_PB', 'USD', DATE '2026-01-01',
                    'MODERATE', 'MEDIUM_TERM', 'DISCRETIONARY', 'SG',
                    'FX_ORIGIN_CLIENT', FALSE, 'ACTIVE'
                );
                INSERT INTO instruments (security_id, name, isin, currency, product_type)
                VALUES ('FX_ORIGIN_SEC', 'FX origin security', 'SG000FXORIGIN', 'XTS', 'EQUITY');
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date, trade_fee,
                    transaction_fx_rate, payload_fingerprint
                ) VALUES
                    ('FX_ORIGIN_LEGACY', 'FX_ORIGIN_PORT', 'FX_ORIGIN_SEC', 'FX_ORIGIN_SEC',
                     'BUY', 1, 100, 100, 'XTS', 'XTS', now(), 0, 2,
                     'sha256:' || repeat('1', 64)),
                    ('FX_ORIGIN_NULL', 'FX_ORIGIN_PORT', 'FX_ORIGIN_SEC', 'FX_ORIGIN_SEC',
                     'BUY', 1, 100, 100, 'XTS', 'XTS', now(), 0, NULL,
                     'sha256:' || repeat('2', 64))
                """
            )
        )

        migration["upgrade"]()
        origins = dict(
            connection.execute(
                text(
                    "SELECT transaction_id, transaction_fx_rate_origin FROM transactions "
                    "WHERE transaction_id LIKE 'FX_ORIGIN_%' ORDER BY transaction_id"
                )
            ).all()
        )
        assert origins == {"FX_ORIGIN_LEGACY": "LEGACY_UNKNOWN", "FX_ORIGIN_NULL": None}
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE transactions SET transaction_fx_rate_origin = 'INVENTED' "
                    "WHERE transaction_id = 'FX_ORIGIN_LEGACY'"
                )
            )

        migration["downgrade"]()
        assert "transaction_fx_rate_origin" not in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }

    with db_engine.connect() as connection:
        assert "transaction_fx_rate_origin" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }
