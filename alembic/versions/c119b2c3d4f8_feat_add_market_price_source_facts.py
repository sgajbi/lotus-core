"""Add append-history exact-scope market-price source facts.

Revision ID: c119b2c3d4f8
Revises: c118b2c3d4f7
Create Date: 2026-07-23 15:52:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c119b2c3d4f8"
down_revision: str | None = "c118b2c3d4f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-history authority without changing legacy market_prices."""

    op.create_table(
        "market_price_source_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("legal_book_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("quote_basis", sa.String(), nullable=False),
        sa.Column("fact_status", sa.String(), nullable=False),
        sa.Column("fact_version", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=False),
        sa.Column("source_revision", sa.String(), nullable=False),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND legal_book_id = btrim(legal_book_id) AND legal_book_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> ''",
            name="ck_market_price_source_fact_scope_normalized",
        ),
        sa.CheckConstraint(
            "price > 0",
            name="ck_market_price_source_fact_price_positive",
        ),
        sa.CheckConstraint(
            "price <> 'NaN'::numeric AND price <> 'Infinity'::numeric",
            name="ck_market_price_source_fact_price_finite",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_market_price_source_fact_currency_normalized",
        ),
        sa.CheckConstraint(
            "quote_basis IN "
            "('UNIT_PRICE', 'PERCENT_OF_PRINCIPAL_CLEAN', "
            "'PERCENT_OF_PRINCIPAL_DIRTY')",
            name="ck_market_price_source_fact_quote_basis",
        ),
        sa.CheckConstraint(
            "fact_status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')",
            name="ck_market_price_source_fact_status",
        ),
        sa.CheckConstraint(
            "fact_version >= 1",
            name="ck_market_price_source_fact_version_positive",
        ),
        sa.CheckConstraint(
            "source_system = btrim(source_system) AND source_system <> '' "
            "AND source_record_id = btrim(source_record_id) AND source_record_id <> '' "
            "AND source_revision = btrim(source_revision) AND source_revision <> ''",
            name="ck_market_price_source_fact_source_normalized",
        ),
        sa.CheckConstraint(
            "source_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_market_price_source_fact_source_hash",
        ),
        sa.CheckConstraint(
            "isfinite(observed_at)",
            name="ck_market_price_source_fact_observed_at_finite",
        ),
        sa.ForeignKeyConstraint(["security_id"], ["instruments.security_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system",
            "source_record_id",
            "fact_version",
            name="uq_market_price_source_fact_version",
        ),
    )
    op.create_index(
        "ix_market_price_fact_scope_history",
        "market_price_source_facts",
        [
            "tenant_id",
            "legal_book_id",
            "security_id",
            "price_date",
            "source_system",
            "source_record_id",
        ],
    )


def downgrade() -> None:
    """Remove scoped market-price authority without touching legacy history."""

    op.drop_index(
        "ix_market_price_fact_scope_history",
        table_name="market_price_source_facts",
    )
    op.drop_table("market_price_source_facts")
