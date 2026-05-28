"""perf add normalized calculation lookup indexes

Revision ID: 9b0c1d2e3f4a
Revises: 8a9b0c1d2e3f
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9b0c1d2e3f4a"
down_revision: str | Sequence[str] | None = "8a9b0c1d2e3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_portfolios_norm_portfolio_id",
        "portfolios",
        [sa.text("trim(portfolio_id)")],
        unique=False,
    )
    op.create_index(
        "ix_pos_hist_norm_port_sec_epoch_date",
        "position_history",
        [
            sa.text("trim(portfolio_id)"),
            sa.text("trim(security_id)"),
            "epoch",
            sa.text("position_date DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_daily_snap_norm_port_sec_date_epoch",
        "daily_position_snapshots",
        [
            sa.text("trim(portfolio_id)"),
            sa.text("trim(security_id)"),
            sa.text("date DESC"),
            sa.text("epoch DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_market_prices_norm_sec_price_date",
        "market_prices",
        [sa.text("trim(security_id)"), sa.text("price_date DESC")],
        unique=False,
    )
    op.create_index(
        "ix_txn_norm_port_sec_date_id",
        "transactions",
        [
            sa.text("trim(portfolio_id)"),
            sa.text("trim(security_id)"),
            "transaction_date",
            "transaction_id",
        ],
        unique=False,
    )
    op.create_index(
        "ix_cashflows_norm_port_sec_date_epoch",
        "cashflows",
        [
            sa.text("trim(portfolio_id)"),
            sa.text("trim(security_id)"),
            "cashflow_date",
            sa.text("epoch DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_position_lot_norm_port_sec",
        "position_lot_state",
        [sa.text("trim(portfolio_id)"), sa.text("trim(security_id)")],
        unique=False,
    )
    op.create_index(
        "ix_pos_ts_norm_port_sec_date_epoch",
        "position_timeseries",
        [
            sa.text("trim(portfolio_id)"),
            sa.text("trim(security_id)"),
            sa.text("date DESC"),
            sa.text("epoch DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_port_ts_norm_port_date_epoch",
        "portfolio_timeseries",
        [sa.text("trim(portfolio_id)"), sa.text("date DESC"), sa.text("epoch DESC")],
        unique=False,
    )
    op.create_index(
        "ix_val_jobs_norm_port_sec_date_epoch_status",
        "portfolio_valuation_jobs",
        [
            sa.text("trim(portfolio_id)"),
            sa.text("trim(security_id)"),
            "valuation_date",
            "epoch",
            "status",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_val_jobs_norm_port_sec_date_epoch_status",
        table_name="portfolio_valuation_jobs",
    )
    op.drop_index("ix_port_ts_norm_port_date_epoch", table_name="portfolio_timeseries")
    op.drop_index("ix_pos_ts_norm_port_sec_date_epoch", table_name="position_timeseries")
    op.drop_index("ix_position_lot_norm_port_sec", table_name="position_lot_state")
    op.drop_index("ix_cashflows_norm_port_sec_date_epoch", table_name="cashflows")
    op.drop_index("ix_txn_norm_port_sec_date_id", table_name="transactions")
    op.drop_index("ix_market_prices_norm_sec_price_date", table_name="market_prices")
    op.drop_index(
        "ix_daily_snap_norm_port_sec_date_epoch",
        table_name="daily_position_snapshots",
    )
    op.drop_index("ix_pos_hist_norm_port_sec_epoch_date", table_name="position_history")
    op.drop_index("ix_portfolios_norm_portfolio_id", table_name="portfolios")
