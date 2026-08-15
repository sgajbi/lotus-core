"""Add durable enterprise security-audit access-decision evidence.

Revision ID: c158b2c3d525
Revises: c157b2c3d524
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c158b2c3d525"
down_revision: str | Sequence[str] | None = "c157b2c3d524"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create one append-only, typed access-decision evidence table."""

    op.create_table(
        "enterprise_security_audit_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("route_template", sa.String(length=256), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("decision", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("required_capability", sa.String(length=128), nullable=True),
        sa.Column("service_identity", sa.String(length=128), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=128), nullable=True),
        sa.Column("identity_posture", sa.String(length=16), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), server_default="1.0", nullable=False),
        sa.Column(
            "classification",
            sa.String(length=64),
            server_default="operational_security_audit",
            nullable=False,
        ),
        sa.CheckConstraint(
            "component IN ('ingestion_service', 'query_service', "
            "'query_control_plane_service', 'financial_reconciliation_service', "
            "'event_replay_service')",
            name="ck_enterprise_security_audit_component",
        ),
        sa.CheckConstraint(
            "method IN ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE')",
            name="ck_enterprise_security_audit_method",
        ),
        sa.CheckConstraint(
            "decision IN ('ALLOW', 'DENY')",
            name="ck_enterprise_security_audit_decision",
        ),
        sa.CheckConstraint(
            "reason IN ('authorized', 'authorization_policy_denied', 'payload_too_large')",
            name="ck_enterprise_security_audit_reason",
        ),
        sa.CheckConstraint(
            "identity_posture IN ('verified', 'unverified')",
            name="ck_enterprise_security_audit_identity_posture",
        ),
        sa.CheckConstraint(
            "(identity_posture = 'verified' AND service_identity IS NOT NULL "
            "AND actor_id IS NOT NULL AND tenant_id IS NOT NULL AND role IS NOT NULL) OR "
            "(identity_posture = 'unverified' AND service_identity IS NULL "
            "AND actor_id IS NULL AND tenant_id IS NULL AND role IS NULL)",
            name="ck_enterprise_security_audit_identity_authority",
        ),
        sa.CheckConstraint(
            "route_template LIKE '/%' AND route_template NOT LIKE '%?%' "
            "AND route_template NOT LIKE '%#%' AND route_template NOT LIKE '%://%'",
            name="ck_enterprise_security_audit_route_template",
        ),
        sa.CheckConstraint(
            "schema_version = '1.0'",
            name="ck_enterprise_security_audit_schema_version",
        ),
        sa.CheckConstraint(
            "classification = 'operational_security_audit'",
            name="ck_enterprise_security_audit_classification",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_enterprise_security_audit_tenant_time_event",
        "enterprise_security_audit_events",
        ["tenant_id", sa.text("occurred_at DESC"), sa.text("event_id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_enterprise_security_audit_tenant_filter_time_event",
        "enterprise_security_audit_events",
        [
            "tenant_id",
            "component",
            "decision",
            sa.text("occurred_at DESC"),
            sa.text("event_id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    """Remove the additive audit table; no historical log reconstruction is attempted."""

    op.drop_index(
        "ix_enterprise_security_audit_tenant_filter_time_event",
        table_name="enterprise_security_audit_events",
    )
    op.drop_index(
        "ix_enterprise_security_audit_tenant_time_event",
        table_name="enterprise_security_audit_events",
    )
    op.drop_table("enterprise_security_audit_events")
