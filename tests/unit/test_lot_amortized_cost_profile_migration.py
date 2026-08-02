"""Executable contract proof for lot amortized-cost profile persistence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, UniqueConstraint

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c139b2c3d50c_feat_add_lot_amortized_cost_profiles.py"
)


def test_lot_amortized_cost_profile_migration_is_reversible(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []

    def record_create_table(name: str, *definitions: Any) -> None:
        operations.append(("create_table", name, definitions))

    def record_create_index(
        name: str,
        table: str,
        columns: list[object],
        **kwargs: object,
    ) -> None:
        operations.append(("create_index", name, table, columns, kwargs))

    monkeypatch.setattr(op, "create_table", record_create_table)
    monkeypatch.setattr(op, "create_index", record_create_index)
    monkeypatch.setattr(
        op,
        "create_unique_constraint",
        lambda name, table, columns: operations.append(
            ("create_unique_constraint", name, table, columns)
        ),
    )
    monkeypatch.setattr(
        op,
        "drop_index",
        lambda name, **kwargs: operations.append(("drop_index", name, kwargs)),
    )
    monkeypatch.setattr(op, "drop_table", lambda name: operations.append(("drop_table", name)))
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop_constraint", name, table, kwargs)),
    )
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    migration["upgrade"]()
    migration["downgrade"]()

    assert migration["revision"] == "c139b2c3d50c"
    assert migration["down_revision"] == "c138b2c3d50b"
    assert [operation[0] for operation in operations] == [
        "create_unique_constraint",
        "create_unique_constraint",
        "create_table",
        "create_index",
        "create_index",
        "create_index",
        "create_table",
        "create_index",
        "drop_index",
        "drop_table",
        "drop_index",
        "drop_index",
        "drop_index",
        "drop_table",
        "drop_constraint",
        "drop_constraint",
    ]

    assert operations[0] == (
        "create_unique_constraint",
        "uq_portfolios_book_scope_identity",
        "portfolios",
        ["tenant_id", "legal_book_id", "portfolio_id"],
    )
    assert operations[1] == (
        "create_unique_constraint",
        "uq_position_lot_scope_identity",
        "position_lot_state",
        ["lot_id", "portfolio_id", "security_id"],
    )

    profile_definitions = operations[2][2]
    profile_columns = {
        definition.name: definition
        for definition in profile_definitions
        if isinstance(definition, Column)
    }
    assert set(profile_columns) == {
        "id",
        "profile_id",
        "profile_version",
        "tenant_id",
        "legal_book_id",
        "portfolio_id",
        "security_id",
        "lot_id",
        "effective_date",
        "status",
        "eligibility_reason",
        "policy_id",
        "policy_version",
        "schedule_version",
        "currency",
        "direction",
        "initial_amortized_cost_local",
        "redemption_value_local",
        "final_amortized_cost_local",
        "residual_local",
        "authority_content_hash",
        "source_references",
        "calculation_lineage",
        "profile_content_hash",
        "created_at",
    }
    assert profile_columns["initial_amortized_cost_local"].type.precision == 18
    assert profile_columns["initial_amortized_cost_local"].type.scale == 10
    assert profile_columns["source_references"].nullable is False
    profile_constraints = {
        definition.name: definition
        for definition in profile_definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_lot_amort_profile_version_positive",
        "ck_lot_amort_profile_scope_normalized",
        "ck_lot_amort_profile_status",
        "ck_lot_amort_profile_direction",
        "ck_lot_amort_profile_currency",
        "ck_lot_amort_profile_policy_version",
        "ck_lot_amort_profile_schedule_version",
        "ck_lot_amort_profile_amounts_finite",
        "ck_lot_amort_profile_initial_nonnegative",
        "ck_lot_amort_profile_redemption_nonnegative",
        "ck_lot_amort_profile_final_nonnegative",
        "ck_lot_amort_profile_authority_hash",
        "ck_lot_amort_profile_content_hash",
        "ck_lot_amort_profile_sources_array",
        "ck_lot_amort_profile_lifecycle_shape",
        "fk_lot_amort_profile_book_scope",
        "fk_lot_amort_profile_security",
        "fk_lot_amort_profile_lot_scope",
        "uq_lot_amort_profile_version",
    } <= profile_constraints.keys()

    period_definitions = operations[6][2]
    period_columns = {
        definition.name: definition
        for definition in period_definitions
        if isinstance(definition, Column)
    }
    assert set(period_columns) == {
        "id",
        "profile_id",
        "profile_version",
        "period_ordinal",
        "period_start_date",
        "period_end_date",
        "year_fraction",
        "period_rate",
        "begin_amortized_cost_local",
        "interest_income_local",
        "cash_coupon_local",
        "amortization_amount_local",
        "end_amortized_cost_local",
        "rounding_adjustment_local",
        "calculation_output_hash",
        "period_content_hash",
        "created_at",
    }
    assert period_columns["year_fraction"].type.precision is None
    assert period_columns["year_fraction"].type.scale is None
    assert period_columns["period_rate"].type.precision is None
    assert period_columns["period_rate"].type.scale is None
    period_constraints = {
        definition.name: definition
        for definition in period_definitions
        if isinstance(definition, (CheckConstraint, ForeignKeyConstraint, UniqueConstraint))
    }
    assert {
        "ck_lot_amort_period_identity_positive",
        "ck_lot_amort_period_date_order",
        "ck_lot_amort_period_amounts_finite",
        "ck_lot_amort_period_amounts_governed",
        "ck_lot_amort_period_hashes",
        "fk_lot_amort_period_profile_version",
        "uq_lot_amort_period_ordinal",
    } <= period_constraints.keys()
    assert operations[-2:] == [
        (
            "drop_constraint",
            "uq_position_lot_scope_identity",
            "position_lot_state",
            {"type_": "unique"},
        ),
        (
            "drop_constraint",
            "uq_portfolios_book_scope_identity",
            "portfolios",
            {"type_": "unique"},
        ),
    ]
