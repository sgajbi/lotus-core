"""feat add fx contract instrument fields

Revision ID: be45fa67b890
Revises: ad34ef56a789
Create Date: 2026-03-09 08:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "be45fa67b890"
down_revision = "ad34ef56a789"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("instruments", sa.Column("portfolio_id", sa.String(), nullable=True))
    op.add_column("instruments", sa.Column("trade_date", sa.Date(), nullable=True))
    op.add_column("instruments", sa.Column("pair_base_currency", sa.String(length=3), nullable=True))
    op.add_column("instruments", sa.Column("pair_quote_currency", sa.String(length=3), nullable=True))
    op.add_column("instruments", sa.Column("buy_currency", sa.String(length=3), nullable=True))
    op.add_column("instruments", sa.Column("sell_currency", sa.String(length=3), nullable=True))
    op.add_column("instruments", sa.Column("buy_amount", sa.Numeric(18, 10), nullable=True))
    op.add_column("instruments", sa.Column("sell_amount", sa.Numeric(18, 10), nullable=True))
    op.add_column("instruments", sa.Column("contract_rate", sa.Numeric(18, 10), nullable=True))
    op.create_index(op.f("ix_instruments_portfolio_id"), "instruments", ["portfolio_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_instruments_portfolio_id_portfolios"),
        "instruments",
        "portfolios",
        ["portfolio_id"],
        ["portfolio_id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_instruments_portfolio_id_portfolios"), "instruments", type_="foreignkey")
    op.drop_index(op.f("ix_instruments_portfolio_id"), table_name="instruments")
    op.drop_column("instruments", "contract_rate")
    op.drop_column("instruments", "sell_amount")
    op.drop_column("instruments", "buy_amount")
    op.drop_column("instruments", "sell_currency")
    op.drop_column("instruments", "buy_currency")
    op.drop_column("instruments", "pair_quote_currency")
    op.drop_column("instruments", "pair_base_currency")
    op.drop_column("instruments", "trade_date")
    op.drop_column("instruments", "portfolio_id")
