"""feat: add durable correlation diagnostics

Revision ID: c100b2c3d4e5
Revises: c100a1b2c3d4
Create Date: 2026-07-06 09:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c100b2c3d4e5"
down_revision: Union[str, None] = "c100a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "processed_events",
    "outbox_events",
    "portfolio_aggregation_jobs",
    "portfolio_valuation_jobs",
    "reprocessing_jobs",
)


def upgrade() -> None:
    for table_name in _TABLES:
        op.add_column(
            table_name, sa.Column("correlation_missing_reason", sa.String(), nullable=True)
        )
        op.add_column(table_name, sa.Column("alternate_lookup_key", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE processed_events
        SET correlation_missing_reason = 'correlation_id_not_supplied',
            alternate_lookup_key = 'processed_event|event_id=' || event_id ||
                '|portfolio_id=' || portfolio_id ||
                '|service_name=' || service_name
        WHERE correlation_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE outbox_events
        SET correlation_missing_reason = 'correlation_id_not_supplied',
            alternate_lookup_key = 'outbox_event|aggregate_id=' || aggregate_id ||
                '|aggregate_type=' || aggregate_type ||
                '|event_type=' || event_type ||
                '|topic=' || topic
        WHERE correlation_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE portfolio_aggregation_jobs
        SET correlation_missing_reason = 'correlation_id_not_supplied',
            alternate_lookup_key = 'aggregation_job|aggregation_date=' ||
                aggregation_date::text || '|portfolio_id=' || portfolio_id
        WHERE correlation_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE portfolio_valuation_jobs
        SET correlation_missing_reason = 'correlation_id_not_supplied',
            alternate_lookup_key = 'valuation_job|epoch=' || epoch::text ||
                '|portfolio_id=' || portfolio_id ||
                '|security_id=' || security_id ||
                '|valuation_date=' || valuation_date::text
        WHERE correlation_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE reprocessing_jobs
        SET correlation_missing_reason = 'correlation_id_not_supplied',
            alternate_lookup_key = 'reprocessing_job|earliest_impacted_date=' ||
                COALESCE(payload->>'earliest_impacted_date', 'unknown') ||
                '|job_type=' || job_type ||
                '|security_id=' || COALESCE(payload->>'security_id', 'unknown')
        WHERE correlation_id IS NULL
        """
    )

    op.create_index(
        "ix_processed_events_alternate_lookup_key",
        "processed_events",
        ["alternate_lookup_key"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_alternate_lookup_key",
        "outbox_events",
        ["alternate_lookup_key"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_aggregation_jobs_alternate_lookup_key",
        "portfolio_aggregation_jobs",
        ["alternate_lookup_key"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_valuation_jobs_alternate_lookup_key",
        "portfolio_valuation_jobs",
        ["alternate_lookup_key"],
        unique=False,
    )
    op.create_index(
        "ix_reprocessing_jobs_alternate_lookup_key",
        "reprocessing_jobs",
        ["alternate_lookup_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reprocessing_jobs_alternate_lookup_key",
        table_name="reprocessing_jobs",
    )
    op.drop_index(
        "ix_portfolio_valuation_jobs_alternate_lookup_key",
        table_name="portfolio_valuation_jobs",
    )
    op.drop_index(
        "ix_portfolio_aggregation_jobs_alternate_lookup_key",
        table_name="portfolio_aggregation_jobs",
    )
    op.drop_index("ix_outbox_events_alternate_lookup_key", table_name="outbox_events")
    op.drop_index("ix_processed_events_alternate_lookup_key", table_name="processed_events")

    for table_name in reversed(_TABLES):
        op.drop_column(table_name, "alternate_lookup_key")
        op.drop_column(table_name, "correlation_missing_reason")
