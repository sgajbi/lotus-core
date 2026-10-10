"""Actual Alembic upgrade refusal preserves retained model source evidence."""

import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from portfolio_common.database_models import ModelPortfolioDefinition, ModelPortfolioTarget
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]
ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "c183b2c3d544"
CURRENT = "c184b2c3d545"
MODEL_ID = "MODEL_WINDOW_MIGRATION"
TABLES = (ModelPortfolioDefinition.__table__, ModelPortfolioTarget.__table__)
NAMES = (
    "ck_model_portfolio_definition_effective_window",
    "ck_model_portfolio_target_effective_window",
)


def _alembic(engine, direction, revision):
    return subprocess.run(
        [sys.executable, "-m", "alembic", direction, revision],
        cwd=ROOT,
        env={**os.environ, "HOST_DATABASE_URL": engine.url.render_as_string(hide_password=False)},
        capture_output=True,
        text=True,
        check=False,
    )


def _version(connection):
    return connection.scalar(text("SELECT version_num FROM alembic_version"))


def _snapshot(connection):
    return tuple(
        [dict(row) for row in connection.execute(select(table).order_by(table.c.id)).mappings()]
        for table in TABLES
    )


def _values(table, invalid=False):
    values = dict(
        model_portfolio_id=MODEL_ID,
        model_portfolio_version="v1",
        effective_from=date(2026, 9, 1),
        effective_to=date(2026, 8, 31) if invalid else date(2026, 9, 1),
        source_system="synthetic_retained_feed",
        source_record_id="RETAINED-ORIGINAL",
        quality_status="accepted",
    )
    if table.name == "model_portfolio_targets":
        values.update(instrument_id="MIGRATION_EQ", target_weight=Decimal("0.6000000000"))
    else:
        values.update(
            display_name="Retained model",
            base_currency="USD",
            risk_profile="balanced",
            mandate_type="discretionary",
            approval_status="approved",
        )
    return values


@pytest.mark.parametrize("invalid_tables", [(0,), (1,), (0, 1)])
def test_actual_upgrade_refuses_retained_invalid_windows_atomically(
    db_engine, clean_db, invalid_tables
):
    downgraded = _alembic(db_engine, "downgrade", PREVIOUS)
    assert downgraded.returncode == 0, downgraded.stderr
    try:
        with db_engine.begin() as connection:
            assert _version(connection) == PREVIOUS
            for index, table in enumerate(TABLES):
                connection.execute(table.insert().values(**_values(table, index in invalid_tables)))
            before = _snapshot(connection)
        refused = _alembic(db_engine, "upgrade", CURRENT)
        assert refused.returncode != 0
        assert "MODEL_PORTFOLIO_INVALID_EFFECTIVE_WINDOW" in refused.stderr
        with db_engine.connect() as connection:
            assert _version(connection) == PREVIOUS
            assert _snapshot(connection) == before
            for table, name in zip(TABLES, NAMES, strict=True):
                assert name not in {
                    item["name"] for item in inspect(connection).get_check_constraints(table.name)
                }
    finally:
        # Only synthetic test-owned rows are removed to restore the fixture schema.
        # Production migration never deletes or rewrites retained rows.
        with db_engine.begin() as connection:
            for table in TABLES:
                connection.execute(table.delete().where(table.c.model_portfolio_id == MODEL_ID))
        restored = _alembic(db_engine, "upgrade", "head")
        assert restored.returncode == 0, restored.stderr


def test_actual_valid_upgrade_preserves_rows_and_enforces_insert_update_checks(db_engine, clean_db):
    downgraded = _alembic(db_engine, "downgrade", PREVIOUS)
    assert downgraded.returncode == 0, downgraded.stderr
    try:
        with db_engine.begin() as connection:
            for table in TABLES:
                connection.execute(table.insert().values(**_values(table)))
            before = _snapshot(connection)
        upgraded = _alembic(db_engine, "upgrade", CURRENT)
        assert upgraded.returncode == 0, upgraded.stderr
        with db_engine.begin() as connection:
            assert _version(connection) == CURRENT
            assert _snapshot(connection) == before
            for table, name in zip(TABLES, NAMES, strict=True):
                assert name in {
                    item["name"] for item in inspect(connection).get_check_constraints(table.name)
                }
                for statement in (
                    table.insert().values(
                        **{**_values(table, True), "model_portfolio_version": "bad"}
                    ),
                    table.update()
                    .where(table.c.model_portfolio_id == MODEL_ID)
                    .values(effective_to=date(2026, 8, 31)),
                ):
                    savepoint = connection.begin_nested()
                    with pytest.raises(IntegrityError, match=name):
                        connection.execute(statement)
                    savepoint.rollback()
                assert _snapshot(connection) == before
            for table in TABLES:
                connection.execute(
                    table.insert().values(
                        **{
                            **_values(table),
                            "model_portfolio_version": "open",
                            "effective_to": None,
                        }
                    )
                )
            assert len(_snapshot(connection)[0]) == len(before[0]) + 1
            assert len(_snapshot(connection)[1]) == len(before[1]) + 1
        repeated = _alembic(db_engine, "upgrade", CURRENT)
        assert repeated.returncode == 0, repeated.stderr
        with db_engine.connect() as connection:
            assert _version(connection) == CURRENT
    finally:
        with db_engine.begin() as connection:
            for table in TABLES:
                connection.execute(table.delete().where(table.c.model_portfolio_id == MODEL_ID))
        restored = _alembic(db_engine, "upgrade", "head")
        assert restored.returncode == 0, restored.stderr
