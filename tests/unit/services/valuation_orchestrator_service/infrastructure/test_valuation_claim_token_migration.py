"""Executable contract proof for the valuation claim-token migration."""

from __future__ import annotations

import runpy
from pathlib import Path

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c151b2c3d518_feat_add_valuation_claim_token.py"
)


def test_valuation_claim_token_is_constrained_reversible_and_linear(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        op,
        "add_column",
        lambda table, column: operations.append(("add_column", table, column)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(
            ("create_check_constraint", name, table, condition)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "drop_column",
        lambda table, column: operations.append(("drop_column", table, column)),
    )

    migration = runpy.run_path(str(MIGRATION))
    assert migration["revision"] == "c151b2c3d518"
    assert migration["down_revision"] == "c150b2c3d517"

    migration["upgrade"]()
    operation, table_name, column = operations.pop(0)
    assert operation == "add_column"
    assert table_name == "portfolio_valuation_jobs"
    assert column.name == "valuation_claim_token"
    assert column.type.length == 32
    assert column.nullable is True
    assert operations.pop(0) == (
        "create_check_constraint",
        "ck_portfolio_valuation_jobs_claim_token",
        "portfolio_valuation_jobs",
        "valuation_claim_token IS NULL OR valuation_claim_token ~ '^[0-9a-f]{32}$'",
    )

    migration["downgrade"]()
    assert operations == [
        (
            "drop_constraint",
            "ck_portfolio_valuation_jobs_claim_token",
            "portfolio_valuation_jobs",
            {"type_": "check"},
        ),
        ("drop_column", "portfolio_valuation_jobs", "valuation_claim_token"),
    ]
