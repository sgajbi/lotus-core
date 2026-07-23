"""PostgreSQL apply/rollback proof for exact-scope market-price authority."""

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
    / "c119b2c3d4f8_feat_add_market_price_source_facts.py"
)

FACT_INSERT = text(
    """
    INSERT INTO market_price_source_facts (
        tenant_id,
        legal_book_id,
        security_id,
        price_date,
        price,
        currency,
        quote_basis,
        fact_status,
        fact_version,
        source_system,
        source_record_id,
        source_revision,
        source_content_hash,
        observed_at
    ) VALUES (
        :tenant_id,
        :legal_book_id,
        'AUTH-BOND-001',
        DATE '2026-07-22',
        :price,
        :currency,
        :quote_basis,
        :fact_status,
        :fact_version,
        'approved-market-data',
        'PRICE-001',
        'revision-7',
        :source_content_hash,
        :observed_at
    )
    """
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _normalize_to_previous_revision(
    migration: dict[str, Any],
    connection,
) -> None:
    """Remove only pre-created c119 state without weakening production downgrade."""

    inspector = inspect(connection)
    if not inspector.has_table("market_price_source_facts"):
        return

    operations = migration["upgrade"].__globals__["op"]
    index_names = {index["name"] for index in inspector.get_indexes("market_price_source_facts")}
    if "ix_market_price_fact_scope_history" in index_names:
        operations.drop_index(
            "ix_market_price_fact_scope_history",
            table_name="market_price_source_facts",
        )
    operations.drop_table("market_price_source_facts")


def test_market_price_source_facts_apply_roll_back_and_enforce_authority(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        _normalize_to_previous_revision(migration, connection)
        assert not inspect(connection).has_table("market_price_source_facts")

        migration["upgrade"]()
        inspector = inspect(connection)
        assert inspector.has_table("market_price_source_facts")
        columns = {column["name"] for column in inspector.get_columns("market_price_source_facts")}
        assert {
            "tenant_id",
            "legal_book_id",
            "security_id",
            "price_date",
            "price",
            "currency",
            "quote_basis",
            "fact_status",
            "fact_version",
            "source_system",
            "source_record_id",
            "source_revision",
            "source_content_hash",
            "observed_at",
        } <= columns
        checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("market_price_source_facts")
        }
        assert {
            "ck_market_price_source_fact_scope_normalized",
            "ck_market_price_source_fact_price_positive",
            "ck_market_price_source_fact_price_finite",
            "ck_market_price_source_fact_currency_normalized",
            "ck_market_price_source_fact_quote_basis",
            "ck_market_price_source_fact_status",
            "ck_market_price_source_fact_version_positive",
            "ck_market_price_source_fact_source_normalized",
            "ck_market_price_source_fact_source_hash",
            "ck_market_price_source_fact_observed_at_finite",
        } <= checks
        unique_constraints = {
            constraint["name"]: constraint
            for constraint in inspector.get_unique_constraints("market_price_source_facts")
        }
        assert unique_constraints["uq_market_price_source_fact_version"]["column_names"] == [
            "source_system",
            "source_record_id",
            "fact_version",
        ]
        indexes = {
            index["name"]: index for index in inspector.get_indexes("market_price_source_facts")
        }
        assert indexes["ix_market_price_fact_scope_history"]["column_names"] == [
            "tenant_id",
            "legal_book_id",
            "security_id",
            "price_date",
            "source_system",
            "source_record_id",
        ]

        connection.execute(
            text(
                """
                INSERT INTO instruments (
                    security_id, name, isin, currency, product_type
                ) VALUES (
                    'AUTH-BOND-001',
                    'Authority Test Bond',
                    'XS000AUTH0001',
                    'USD',
                    'BOND'
                )
                """
            )
        )
        valid = {
            "tenant_id": "TENANT-SG",
            "legal_book_id": "PB-SG-01",
            "price": "99.25",
            "currency": "USD",
            "quote_basis": "PERCENT_OF_PRINCIPAL_CLEAN",
            "fact_status": "ACTIVE",
            "fact_version": 1,
            "source_content_hash": "a" * 64,
            "observed_at": "2026-07-23 04:30:00+00",
        }
        connection.execute(FACT_INSERT, valid)

        invalid_overrides = [
            {"tenant_id": " TENANT-SG ", "fact_version": 2},
            {"price": "0", "fact_version": 2},
            {"price": "NaN", "fact_version": 2},
            {"price": "Infinity", "fact_version": 2},
            {"price": "-Infinity", "fact_version": 2},
            {"currency": "usd", "fact_version": 2},
            {"quote_basis": "PERCENT", "fact_version": 2},
            {"fact_status": "DELETED", "fact_version": 2},
            {"fact_version": 0},
            {"source_content_hash": "NOT-A-HASH", "fact_version": 2},
            {"observed_at": "infinity", "fact_version": 2},
            {"observed_at": "-infinity", "fact_version": 2},
        ]
        for overrides in invalid_overrides:
            savepoint = connection.begin_nested()
            with pytest.raises(DatabaseError):
                connection.execute(FACT_INSERT, valid | overrides)
            savepoint.rollback()

        duplicate = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(FACT_INSERT, valid)
        duplicate.rollback()

        migration["downgrade"]()
        assert not inspect(connection).has_table("market_price_source_facts")

        migration["upgrade"]()
        final_inspector = inspect(connection)
        assert final_inspector.has_table("market_price_source_facts")
        assert "ix_market_price_fact_scope_history" in {
            index["name"] for index in final_inspector.get_indexes("market_price_source_facts")
        }
