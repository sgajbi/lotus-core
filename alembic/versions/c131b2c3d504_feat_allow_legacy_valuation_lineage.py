"""Allow bounded calculation lineage on legacy valuation receipts.

Revision ID: c131b2c3d504
Revises: c130b2c3d503
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c131b2c3d504"
down_revision: str | Sequence[str] | None = "c130b2c3d503"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_daily_position_valuation_receipt_evidence_complete"
_SUPPORTED_OR_LEGACY_WITH_OPTIONAL_LINEAGE = (
    "("
    "supportability = 'SUPPORTED' "
    "AND policy_id IS NOT NULL AND btrim(policy_id) <> '' "
    "AND policy_version >= 1 AND assignment_version >= 1 "
    "AND assignment_content_hash IS NOT NULL "
    "AND policy_assignment_source IS NOT NULL "
    "AND quote_basis IS NOT NULL "
    "AND price_fact_version >= 1 AND price_fact_content_hash IS NOT NULL "
    "AND market_price_source IS NOT NULL AND calculation_lineage IS NOT NULL"
    ") OR ("
    "supportability = 'LEGACY_UNSCOPED' "
    "AND policy_id IS NULL AND policy_version IS NULL "
    "AND assignment_version IS NULL AND assignment_content_hash IS NULL "
    "AND policy_assignment_source IS NULL AND quote_basis IS NULL "
    "AND price_fact_version IS NULL AND price_fact_content_hash IS NULL "
    "AND market_price_source IS NULL"
    ")"
)
_SUPPORTED_OR_LEGACY_WITHOUT_LINEAGE = (
    "("
    "supportability = 'SUPPORTED' "
    "AND policy_id IS NOT NULL AND btrim(policy_id) <> '' "
    "AND policy_version >= 1 AND assignment_version >= 1 "
    "AND assignment_content_hash IS NOT NULL "
    "AND policy_assignment_source IS NOT NULL "
    "AND quote_basis IS NOT NULL "
    "AND price_fact_version >= 1 AND price_fact_content_hash IS NOT NULL "
    "AND market_price_source IS NOT NULL AND calculation_lineage IS NOT NULL"
    ") OR ("
    "supportability = 'LEGACY_UNSCOPED' "
    "AND policy_id IS NULL AND policy_version IS NULL "
    "AND assignment_version IS NULL AND assignment_content_hash IS NULL "
    "AND policy_assignment_source IS NULL AND quote_basis IS NULL "
    "AND price_fact_version IS NULL AND price_fact_content_hash IS NULL "
    "AND market_price_source IS NULL AND calculation_lineage IS NULL"
    ")"
)


def upgrade() -> None:
    """Permit optional numeric calculation evidence without source-authority claims."""

    op.drop_constraint(
        _CONSTRAINT_NAME,
        "daily_position_valuation_receipts",
        type_="check",
    )
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "daily_position_valuation_receipts",
        _SUPPORTED_OR_LEGACY_WITH_OPTIONAL_LINEAGE,
    )


def downgrade() -> None:
    """Restore the prior legacy receipt invariant without retaining new-only evidence."""

    op.drop_constraint(
        _CONSTRAINT_NAME,
        "daily_position_valuation_receipts",
        type_="check",
    )
    op.execute(
        "UPDATE daily_position_valuation_receipts "
        "SET calculation_lineage = NULL "
        "WHERE supportability = 'LEGACY_UNSCOPED' "
        "AND calculation_lineage IS NOT NULL"
    )
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "daily_position_valuation_receipts",
        _SUPPORTED_OR_LEGACY_WITHOUT_LINEAGE,
    )
