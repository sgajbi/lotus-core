"""Execute the valuation-owner cutover and atomic historical refusal on PostgreSQL."""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from portfolio_common.database_models import Portfolio
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_support.valuation_job_migration_dependencies import (
    downgrade_valuation_job_schema,
    restore_valuation_job_schema,
    valuation_job_schema_semantics,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.lifecycle]
ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "c184b2c3d545"
CURRENT = "c185b2c3d546"
OWNERS = (("VALUATION_MIGRATION", "tenant-a"), (" VALUATION_MIGRATION ", "tenant-b"))


def _alembic(engine, direction, revision):
    return subprocess.run(
        [sys.executable, "-m", "alembic", direction, revision],
        cwd=ROOT,
        env={**os.environ, "HOST_DATABASE_URL": engine.url.render_as_string(hide_password=False)},
        capture_output=True,
        text=True,
        check=False,
    )


def _snapshot(connection):
    return [
        dict(row)
        for row in connection.execute(
            text("SELECT * FROM portfolio_valuation_jobs ORDER BY id")
        ).mappings()
    ]


def _seed_roots(connection):
    for portfolio, tenant in OWNERS:
        connection.execute(
            Portfolio.__table__.insert().values(
                portfolio_id=portfolio,
                tenant_id=tenant,
                base_currency="USD",
                open_date=date(2026, 10, 9),
                risk_exposure="balanced",
                investment_time_horizon="long",
                portfolio_type="advisory",
                booking_center_code="SG",
                client_id=f"client-{tenant}",
                status="ACTIVE",
            )
        )


def _stage_legacy(connection, portfolio):
    connection.execute(
        text("""
        INSERT INTO portfolio_valuation_jobs
            (portfolio_id, security_id, valuation_date, epoch, status, correlation_id)
        VALUES (:portfolio, 'SEC', '2026-10-09', 3, 'PENDING', 'retained-original')
    """),
        {"portfolio": portfolio},
    )


def _restore(engine):
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM portfolio_valuation_jobs WHERE portfolio_id = ANY(:identities)"),
            {
                "identities": [
                    *[portfolio for portfolio, _tenant in OWNERS],
                    "MISSING_VALUATION_ROOT",
                    "VALUATION_MIGRATION  ",
                ]
            },
        )
        connection.execute(
            Portfolio.__table__.delete().where(
                Portfolio.portfolio_id.in_([portfolio for portfolio, _tenant in OWNERS])
            )
        )
    restored = _alembic(engine, "upgrade", "head")
    assert restored.returncode == 0, restored.stderr


def test_actual_cutover_preserves_exact_source_identities_and_enforces_owner(db_engine, clean_db):
    previous = _alembic(db_engine, "downgrade", PREVIOUS)
    assert previous.returncode == 0, previous.stderr
    try:
        with db_engine.begin() as connection:
            _seed_roots(connection)
            for portfolio, _tenant in OWNERS:
                _stage_legacy(connection, portfolio)
            before = _snapshot(connection)
        upgraded = _alembic(db_engine, "upgrade", CURRENT)
        assert upgraded.returncode == 0, upgraded.stderr
        with db_engine.connect() as connection:
            after = _snapshot(connection)
            assert [row.pop("tenant_id") for row in after] == [
                dict(OWNERS)[row["portfolio_id"]] for row in before
            ]
            assert after == before
            constraints = inspect(connection).get_unique_constraints("portfolio_valuation_jobs")
            assert any(
                item["column_names"]
                == ["tenant_id", "portfolio_id", "security_id", "valuation_date", "epoch"]
                for item in constraints
            )
        with pytest.raises(IntegrityError):
            with db_engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE portfolio_valuation_jobs SET tenant_id = 'tenant-b' "
                        "WHERE portfolio_id = :portfolio"
                    ),
                    {"portfolio": OWNERS[0][0]},
                )
    finally:
        _restore(db_engine)


@pytest.mark.parametrize("invalid_setup", ["missing-owner-key", "retained-work"])
def test_historical_root_fixture_refuses_invalid_setup_and_restores_actual_owner_schema(
    db_engine, clean_db, invalid_setup
):
    with db_engine.begin() as connection:
        before = valuation_job_schema_semantics(connection)
        invalid = connection.begin_nested()
        if invalid_setup == "missing-owner-key":
            connection.execute(
                text(
                    "ALTER TABLE portfolio_valuation_jobs "
                    "DROP CONSTRAINT fk_portfolio_valuation_jobs_tenant_portfolio"
                )
            )
            expected_refusal = "requires valuation-job owner authority"
        else:
            _seed_roots(connection)
            connection.execute(
                text(
                    "INSERT INTO portfolio_valuation_jobs "
                    "(tenant_id, portfolio_id, security_id, valuation_date, epoch, status) "
                    "VALUES (:tenant, :portfolio, 'SEC', '2026-10-09', 3, 'PENDING')"
                ),
                {"tenant": OWNERS[0][1], "portfolio": OWNERS[0][0]},
            )
            expected_refusal = "requires empty valuation jobs"
        retained = _snapshot(connection)
        try:
            with pytest.raises(AssertionError, match=expected_refusal):
                downgrade_valuation_job_schema(connection)
            assert _snapshot(connection) == retained
            assert "tenant_id" in {
                column["name"]
                for column in inspect(connection).get_columns("portfolio_valuation_jobs")
            }
        finally:
            invalid.rollback()
        assert valuation_job_schema_semantics(connection) == before

        migration = downgrade_valuation_job_schema(connection)

    # The aggregation lock proof descends and restores in different transactions/connections.
    assert connection.closed
    with db_engine.begin() as connection:
        restore_valuation_job_schema(migration, connection)
        assert valuation_job_schema_semantics(connection) == before


@pytest.mark.parametrize("unowned_portfolio", ["MISSING_VALUATION_ROOT", "VALUATION_MIGRATION  "])
def test_actual_upgrade_refuses_orphan_or_trim_ambiguous_history_atomically(
    db_engine, clean_db, unowned_portfolio
):
    previous = _alembic(db_engine, "downgrade", PREVIOUS)
    assert previous.returncode == 0, previous.stderr
    try:
        with db_engine.begin() as connection:
            _seed_roots(connection)
            _stage_legacy(connection, OWNERS[0][0])
            _stage_legacy(connection, unowned_portfolio)
            before = _snapshot(connection)
        refused = _alembic(db_engine, "upgrade", CURRENT)
        assert refused.returncode != 0
        assert "valuation-job tenant cutover found unprovable ownership" in refused.stderr
        with db_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == PREVIOUS
            assert _snapshot(connection) == before
            assert "tenant_id" not in {
                column["name"]
                for column in inspect(connection).get_columns("portfolio_valuation_jobs")
            }
    finally:
        _restore(db_engine)
