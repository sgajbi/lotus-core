"""Executable contract proof for durable enterprise security-audit evidence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from portfolio_common.database_models import EnterpriseSecurityAuditEvent
from sqlalchemy import CheckConstraint

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c158b2c3d525_feat_add_enterprise_security_audit_events.py"
)


def test_security_audit_model_has_closed_typed_evidence_without_json() -> None:
    table = EnterpriseSecurityAuditEvent.__table__

    assert table.name == "enterprise_security_audit_events"
    assert table.primary_key.columns.keys() == ["event_id"]
    assert all(column.type.__class__.__name__ not in {"JSON", "JSONB"} for column in table.columns)
    assert {index.name for index in table.indexes} == {
        "ix_enterprise_security_audit_tenant_time_event",
        "ix_enterprise_security_audit_tenant_filter_time_event",
    }
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert set(checks) == {
        "ck_enterprise_security_audit_component",
        "ck_enterprise_security_audit_method",
        "ck_enterprise_security_audit_decision",
        "ck_enterprise_security_audit_reason",
        "ck_enterprise_security_audit_identity_posture",
        "ck_enterprise_security_audit_identity_authority",
        "ck_enterprise_security_audit_route_template",
        "ck_enterprise_security_audit_schema_version",
        "ck_enterprise_security_audit_classification",
    }
    assert "metadata" not in table.columns
    assert "payload" not in table.columns


def test_security_audit_migration_is_single_head_typed_and_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "create_table",
        lambda name, *items, **kwargs: operations.append(("create_table", name, items, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "create_index",
        lambda name, table, columns, **kwargs: operations.append(
            ("create_index", name, table, columns, kwargs)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_table",
        lambda name: operations.append(("drop_table", name)),
    )

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c158b2c3d525"
    assert migration["down_revision"] == "c157b2c3d524"
    create_table = next(operation for operation in operations if operation[0] == "create_table")
    assert create_table[1] == "enterprise_security_audit_events"
    columns = [item for item in create_table[2] if item.__class__.__name__ == "Column"]
    assert len(columns) == 18
    assert all(column.type.__class__.__name__ not in {"JSON", "JSONB"} for column in columns)
    assert [operation[1] for operation in operations if operation[0] == "create_index"] == [
        "ix_enterprise_security_audit_tenant_time_event",
        "ix_enterprise_security_audit_tenant_filter_time_event",
    ]
    assert [operation[1] for operation in operations if operation[0] == "drop_index"] == [
        "ix_enterprise_security_audit_tenant_filter_time_event",
        "ix_enterprise_security_audit_tenant_time_event",
    ]
    assert operations[-1] == ("drop_table", "enterprise_security_audit_events")
