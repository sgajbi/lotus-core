"""Backfill current-epoch control state for legacy position evidence.

Revision ID: c159b2c3d526
Revises: c158b2c3d525
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c159b2c3d526"
down_revision: str | Sequence[str] | None = "c158b2c3d525"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEGACY_POSITION_STATE_BACKFILL = sa.text(
    """
    WITH legacy_position_evidence AS (
        SELECT
            portfolio_id,
            btrim(security_id) AS security_id,
            epoch,
            position_date AS evidence_date,
            'history' AS evidence_kind
        FROM position_history
        WHERE btrim(portfolio_id) <> ''
          AND btrim(security_id) <> ''

        UNION ALL

        SELECT
            portfolio_id,
            btrim(security_id) AS security_id,
            epoch,
            date AS evidence_date,
            'snapshot' AS evidence_kind
        FROM daily_position_snapshots
        WHERE btrim(portfolio_id) <> ''
          AND btrim(security_id) <> ''
    ),
    latest_evidence_epoch AS (
        SELECT portfolio_id, security_id, max(epoch) AS epoch
        FROM legacy_position_evidence
        GROUP BY portfolio_id, security_id
    ),
    missing_state_rows AS (
        SELECT
            evidence.portfolio_id,
            evidence.security_id,
            evidence.epoch,
            CASE
                WHEN bool_or(evidence.evidence_kind = 'history') THEN
                    CASE
                        WHEN min(evidence.evidence_date)
                             FILTER (WHERE evidence.evidence_kind = 'history') > DATE '0001-01-01'
                            THEN min(evidence.evidence_date)
                                 FILTER (WHERE evidence.evidence_kind = 'history') - 1
                        ELSE min(evidence.evidence_date)
                             FILTER (WHERE evidence.evidence_kind = 'history')
                    END
                ELSE max(evidence.evidence_date)
                     FILTER (WHERE evidence.evidence_kind = 'snapshot')
            END AS watermark_date,
            CASE
                WHEN bool_or(evidence.evidence_kind = 'history') THEN 'REPROCESSING'
                ELSE 'CURRENT'
            END AS status
        FROM legacy_position_evidence AS evidence
        JOIN latest_evidence_epoch AS latest
          ON latest.portfolio_id = evidence.portfolio_id
         AND latest.security_id = evidence.security_id
         AND latest.epoch = evidence.epoch
        WHERE NOT EXISTS (
            SELECT 1
            FROM position_state AS existing
            WHERE existing.portfolio_id = evidence.portfolio_id
              AND btrim(existing.security_id) = evidence.security_id
        )
        GROUP BY evidence.portfolio_id, evidence.security_id, evidence.epoch
    )
    INSERT INTO position_state (
        portfolio_id,
        security_id,
        epoch,
        watermark_date,
        status,
        created_at,
        updated_at
    )
    SELECT
        portfolio_id,
        security_id,
        epoch,
        watermark_date,
        status,
        now(),
        now()
    FROM missing_state_rows
    ON CONFLICT (portfolio_id, security_id) DO NOTHING
    """
)


def upgrade() -> None:
    """Restore conservative replay authority for position evidence created before state control."""

    op.execute(LEGACY_POSITION_STATE_BACKFILL)


def downgrade() -> None:
    """Retain repaired state because provenance cannot distinguish it from later live updates."""

    # This data repair is intentionally irreversible. Deleting a row during downgrade could
    # remove state that a live processor advanced after the upgrade committed.
    return None
