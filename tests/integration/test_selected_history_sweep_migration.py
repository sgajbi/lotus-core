"""Execute the historical-control sweep marker cutover on real PostgreSQL."""

from __future__ import annotations

import runpy
from datetime import date
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import Portfolio, PortfolioAggregationJob
from portfolio_common.portfolio_aggregation_job_schema import (
    PortfolioSelectedHistoryObservation,
    PortfolioSelectedHistoryValuationState,
)
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scripts.validation.docker_endpoint_smoke import build_smoke_cleanup_sql
from tests.test_support.tenant import TEST_LEGAL_BOOK_ID, TEST_TENANT_ID
from tools.front_office_portfolio_seed import build_portfolio_seed_cleanup_sql

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.lifecycle]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c171b2c3d532_feat_fence_selected_history_sweeps.py"
)
VALIDATION_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c172b2c3d533_validate_selected_history_job_checks.py"
)


def _check_validation_states(connection) -> dict[str, bool]:
    return dict(
        connection.execute(
            text(
                "SELECT conname, convalidated FROM pg_constraint "
                "WHERE conrelid = 'portfolio_aggregation_jobs'::regclass "
                "AND conname IN ("
                "'ck_portfolio_aggregation_jobs_selected_history_sweep_epoch', "
                "'ck_portfolio_aggregation_jobs_selected_history_collective_epoch')"
            )
        ).all()
    )


@pytest.mark.usefixtures("clean_db")
def test_sweep_marker_upgrade_defaults_existing_jobs_and_rolls_back(db_engine) -> None:
    portfolio_id = "HISTORICAL-SWEEP-MIGRATION"
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                legal_book_id=TEST_LEGAL_BOOK_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT-HIST-SWEEP-MIGRATION",
                status="ACTIVE",
            )
        )
        session.add(
            PortfolioAggregationJob(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                aggregation_date=date(2025, 4, 20),
                status="COMPLETE",
                target_epoch=4,
                source_revision=7,
            )
        )
        session.commit()

    migration = runpy.run_path(str(MIGRATION))
    validation = runpy.run_path(str(VALIDATION_MIGRATION))
    index_ddl: list[str] = []

    def capture_index_ddl(_connection, _cursor, statement, _parameters, _context, _many):
        if "ix_position_history_portfolio_strip_security_date_id" in statement:
            index_ddl.append(statement)

    event.listen(db_engine, "before_cursor_execute", capture_index_ddl)
    with db_engine.connect() as connection:
        operations = Operations(MigrationContext.configure(connection))
        migration["upgrade"].__globals__["op"] = operations
        migration["downgrade"].__globals__["op"] = operations
        validation["upgrade"].__globals__["op"] = operations
        validation["downgrade"].__globals__["op"] = operations
        try:
            migration["downgrade"]()
            connection.commit()
            previous_columns = {
                column["name"]
                for column in inspect(connection).get_columns("portfolio_aggregation_jobs")
            }
            assert "selected_history_sweep_epoch" not in previous_columns
            assert "selected_history_collective_epoch" not in previous_columns
            assert (
                "portfolio_selected_history_observations"
                not in inspect(connection).get_table_names()
            )
            assert (
                "portfolio_selected_history_valuation_states"
                not in inspect(connection).get_table_names()
            )
            assert "ix_position_history_portfolio_strip_security_date_id" not in {
                index["name"] for index in inspect(connection).get_indexes("position_history")
            }

            connection.rollback()  # Inspector reads start a transaction; concurrent DDL cannot.
            migration["upgrade"]()
            connection.commit()
            current_columns = {
                column["name"]
                for column in inspect(connection).get_columns("portfolio_aggregation_jobs")
            }
            assert {
                "selected_history_sweep_epoch",
                "selected_history_collective_epoch",
            } <= current_columns
            assert (
                "portfolio_selected_history_observations" in inspect(connection).get_table_names()
            )
            assert (
                "portfolio_selected_history_valuation_states"
                in inspect(connection).get_table_names()
            )
            observation_indexes = {
                index["name"]
                for index in inspect(connection).get_indexes(
                    "portfolio_selected_history_observations"
                )
            }
            assert "ix_portfolio_selected_history_observations_fact" in observation_indexes
            nested = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO portfolio_selected_history_valuation_states "
                        "(tenant_id, portfolio_id, security_id, position_history_id, "
                        "selected_business_date, source_fact, valuation_outcome, "
                        "valuation_epoch, valuation_date) "
                        "VALUES (:tenant_id, :portfolio_id, 'HIST-SECURITY', 1, "
                        ":as_of_date, 'fact', 'UNKNOWN', 1, :as_of_date)"
                    ),
                    {
                        "tenant_id": TEST_TENANT_ID,
                        "portfolio_id": portfolio_id,
                        "as_of_date": date(2025, 4, 20),
                    },
                )
            nested.rollback()
            nested = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO portfolio_selected_history_valuation_states "
                        "(tenant_id, portfolio_id, security_id, position_history_id, "
                        "selected_business_date, source_fact, valuation_outcome, "
                        "valuation_epoch, valuation_date) "
                        "VALUES (:tenant_id, :portfolio_id, 'HIST-SECURITY', 1, "
                        ":as_of_date, 'fact', 'READY', -1, :as_of_date)"
                    ),
                    {
                        "tenant_id": TEST_TENANT_ID,
                        "portfolio_id": portfolio_id,
                        "as_of_date": date(2025, 4, 20),
                    },
                )
            nested.rollback()
            assert "ix_position_history_portfolio_strip_security_date_id" in {
                index["name"] for index in inspect(connection).get_indexes("position_history")
            }
            existing = connection.execute(
                text(
                    "SELECT target_epoch, source_revision, status, "
                    "selected_history_sweep_epoch, selected_history_collective_epoch "
                    "FROM portfolio_aggregation_jobs WHERE portfolio_id = :portfolio_id"
                ),
                {"portfolio_id": portfolio_id},
            ).one()
            assert tuple(existing) == (4, 7, "COMPLETE", -1, 0)

            for column, invalid_value in (
                ("selected_history_sweep_epoch", -2),
                ("selected_history_collective_epoch", -1),
            ):
                nested = connection.begin_nested()
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text(
                            f"UPDATE portfolio_aggregation_jobs SET {column} = :invalid_value "
                            "WHERE portfolio_id = :portfolio_id"
                        ),
                        {"invalid_value": invalid_value, "portfolio_id": portfolio_id},
                    )
                nested.rollback()
            assert set(_check_validation_states(connection).values()) == {False}
            connection.rollback()
            connection.execute(
                text(
                    "ALTER TABLE portfolio_aggregation_jobs DROP CONSTRAINT "
                    "ck_portfolio_aggregation_jobs_selected_history_sweep_epoch"
                )
            )
            connection.execute(
                text(
                    "UPDATE portfolio_aggregation_jobs SET selected_history_sweep_epoch = -2 "
                    "WHERE portfolio_id = :portfolio_id"
                ),
                {"portfolio_id": portfolio_id},
            )
            connection.execute(
                text(
                    "ALTER TABLE portfolio_aggregation_jobs ADD CONSTRAINT "
                    "ck_portfolio_aggregation_jobs_selected_history_sweep_epoch "
                    "CHECK (selected_history_sweep_epoch >= -1) NOT VALID"
                )
            )
            connection.commit()
            with pytest.raises(IntegrityError):
                validation["upgrade"]()
            connection.rollback()
            connection.execute(
                text(
                    "UPDATE portfolio_aggregation_jobs SET selected_history_sweep_epoch = -1 "
                    "WHERE portfolio_id = :portfolio_id"
                ),
                {"portfolio_id": portfolio_id},
            )
            connection.commit()
            validation["upgrade"]()
            assert set(_check_validation_states(connection).values()) == {True}
            connection.rollback()
            validation["downgrade"]()
            connection.commit()
            assert set(_check_validation_states(connection).values()) == {False}
            connection.rollback()
            validation["upgrade"]()
            assert set(_check_validation_states(connection).values()) == {True}
            connection.rollback()
            migration["_create_history_index"]()
            assert sum("CREATE INDEX CONCURRENTLY" in statement for statement in index_ddl) == 1

            governed_keys = [
                "portfolio_id",
                text(f"btrim(security_id, {migration['_PYTHON_STRIP_BOUNDARY_SQL']})"),
                text("position_date DESC"),
                text("id DESC"),
            ]
            for wrong_keys, predicate in (
                (["portfolio_id"], None),
                (governed_keys, text("epoch >= 0")),
            ):
                migration["_drop_history_index"]()
                with operations.get_context().autocommit_block():
                    operations.create_index(
                        "ix_position_history_portfolio_strip_security_date_id",
                        "position_history",
                        wrong_keys,
                        postgresql_where=predicate,
                        postgresql_concurrently=True,
                    )
                try:
                    with pytest.raises(RuntimeError, match="unexpected keys"):
                        migration["_create_history_index"]()
                finally:
                    migration["_drop_history_index"]()
                    migration["_create_history_index"]()

            migration["_drop_history_index"]()
            with operations.get_context().autocommit_block():
                operations.create_index(
                    "ix_position_history_portfolio_strip_security_date_id",
                    "portfolios",
                    ["portfolio_id"],
                    postgresql_concurrently=True,
                )
            try:
                with pytest.raises(RuntimeError, match="belongs to another table"):
                    migration["_create_history_index"]()
            finally:
                migration["_drop_history_index"]()
                migration["_create_history_index"]()
        finally:
            connection.rollback()
            if (
                "portfolio_selected_history_observations"
                not in inspect(connection).get_table_names()
            ):
                connection.rollback()
                migration["upgrade"]()
                connection.commit()
            event.remove(db_engine, "before_cursor_execute", capture_index_ddl)
    assert any("CREATE INDEX CONCURRENTLY" in statement for statement in index_ddl)
    assert any("DROP INDEX CONCURRENTLY" in statement for statement in index_ddl)


@pytest.mark.usefixtures("clean_db")
def test_canonical_portfolio_reseed_clears_selected_history_observations(db_engine) -> None:
    target_portfolio_id = "HISTORICAL-RESEED-TARGET"
    other_portfolio_id = "HISTORICAL-RESEED-OTHER"
    with Session(db_engine) as session:
        for portfolio_id in (target_portfolio_id, other_portfolio_id):
            session.add(
                Portfolio(
                    tenant_id=TEST_TENANT_ID,
                    legal_book_id=TEST_LEGAL_BOOK_ID,
                    portfolio_id=portfolio_id,
                    base_currency="USD",
                    open_date=date(2025, 1, 1),
                    risk_exposure="balanced",
                    investment_time_horizon="long_term",
                    portfolio_type="discretionary",
                    booking_center_code="SG",
                    client_id=f"CLIENT-{portfolio_id}",
                    status="ACTIVE",
                )
            )
            session.add(
                PortfolioSelectedHistoryObservation(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    as_of_date=date(2026, 4, 10),
                    security_id="HIST-RESEED-SECURITY",
                    position_history_id=None,
                    selected_business_date=None,
                    selected_nonzero=False,
                    source_fact=None,
                )
            )
            session.add(
                PortfolioSelectedHistoryValuationState(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    security_id="HIST-RESEED-SECURITY",
                    position_history_id=1,
                    selected_business_date=date(2026, 4, 10),
                    source_fact="reseed-fact",
                    valuation_outcome="READY",
                    valuation_epoch=1,
                    valuation_date=date(2026, 4, 10),
                )
            )
        session.commit()

    with db_engine.begin() as connection:
        for statement in build_portfolio_seed_cleanup_sql(portfolio_id=target_portfolio_id).split(
            ";"
        ):
            if statement.strip():
                connection.execute(text(statement))

        assert (
            connection.scalar(
                text("SELECT count(*) FROM portfolios WHERE portfolio_id = :portfolio_id"),
                {"portfolio_id": target_portfolio_id},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM portfolio_selected_history_observations "
                    "WHERE portfolio_id = :portfolio_id"
                ),
                {"portfolio_id": target_portfolio_id},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM portfolio_selected_history_observations "
                    "WHERE portfolio_id = :portfolio_id"
                ),
                {"portfolio_id": other_portfolio_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM portfolio_selected_history_valuation_states "
                    "WHERE portfolio_id = :portfolio_id"
                ),
                {"portfolio_id": target_portfolio_id},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM portfolio_selected_history_valuation_states "
                    "WHERE portfolio_id = :portfolio_id"
                ),
                {"portfolio_id": other_portfolio_id},
            )
            == 1
        )


@pytest.mark.usefixtures("clean_db")
def test_endpoint_smoke_reseed_clears_selected_history_children(db_engine) -> None:
    smoke_portfolio_id = "PORT_SMOKE_CANONICAL_TEST"
    unrelated_portfolio_id = "HISTORICAL-SMOKE-OTHER"
    with Session(db_engine) as session:
        for portfolio_id in (smoke_portfolio_id, unrelated_portfolio_id):
            session.add(
                Portfolio(
                    tenant_id=TEST_TENANT_ID,
                    legal_book_id=TEST_LEGAL_BOOK_ID,
                    portfolio_id=portfolio_id,
                    base_currency="USD",
                    open_date=date(2025, 1, 1),
                    risk_exposure="balanced",
                    investment_time_horizon="long_term",
                    portfolio_type="discretionary",
                    booking_center_code="SG",
                    client_id=f"CLIENT-{portfolio_id}",
                    status="ACTIVE",
                )
            )
            session.add(
                PortfolioSelectedHistoryObservation(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    as_of_date=date(2026, 4, 10),
                    security_id="HIST-SMOKE-SECURITY",
                    position_history_id=None,
                    selected_business_date=None,
                    selected_nonzero=False,
                    source_fact=None,
                )
            )
            session.add(
                PortfolioSelectedHistoryValuationState(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    security_id="HIST-SMOKE-SECURITY",
                    position_history_id=1,
                    selected_business_date=date(2026, 4, 10),
                    source_fact="smoke-fact",
                    valuation_outcome="UNAVAILABLE",
                    valuation_epoch=1,
                    valuation_date=date(2026, 4, 10),
                )
            )
        session.commit()

    with db_engine.begin() as connection:
        for statement in build_smoke_cleanup_sql().split(";"):
            if statement.strip().lower() not in ("", "begin", "commit"):
                connection.execute(text(statement))

    with db_engine.connect() as connection:
        for table_name in (
            "portfolios",
            "portfolio_selected_history_observations",
            "portfolio_selected_history_valuation_states",
        ):
            assert (
                connection.scalar(
                    text(f"SELECT count(*) FROM {table_name} WHERE portfolio_id = :portfolio_id"),
                    {"portfolio_id": smoke_portfolio_id},
                )
                == 0
            )
            assert (
                connection.scalar(
                    text(f"SELECT count(*) FROM {table_name} WHERE portfolio_id = :portfolio_id"),
                    {"portfolio_id": unrelated_portfolio_id},
                )
                == 1
            )
