"""Executable contract for the corporate-action authority fix-forward migration."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c155b2c3d522_fix_forward_corporate_action_authority.py"
)


def test_authority_fix_forward_accepts_legacy_and_enforces_new_book_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []
    monkeypatch.setattr(op, "execute", lambda statement: statements.append(str(statement)))

    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c155b2c3d522"
    assert migration["down_revision"] == "c154b2c3d521"
    sql = "\n".join(statements)
    assert "CREATE OR REPLACE FUNCTION canonical_ca_manifest_payload_hash" in sql
    assert "book_scoped_payload" in sql
    assert "'tenant_id', 'version'" in sql
    assert "'source_reference', 'version'" in sql
    assert "CREATE TRIGGER trg_ca_manifest_payload_book_scope" in sql
    assert "manifest payload book scope conflicts with parent event" in sql
    assert "DROP TRIGGER trg_ca_manifest_payload_book_scope" in sql
    assert "DROP FUNCTION enforce_ca_manifest_payload_book_scope()" in sql
