"""Native owned test reset preserves real immutable dependency semantics."""

from datetime import date
from uuid import uuid4

import pytest
from portfolio_common.database_models import Portfolio
from portfolio_common.database_runtime_profile import DatabasePoolMode
from portfolio_common.db import create_async_database_engine
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests import conftest as harness
from tests.integration.services.ingestion_service import (
    test_portfolio_source_observation_admission_postgresql as observation_proof,
)
from tests.integration.services.ingestion_service import (
    test_portfolio_source_verification_postgresql as verification_proof,
)
from tests.test_support.db_cleanup import (
    authorize_database_cleanup,
    require_database_cleanup_authorization,
)
from tests.test_support.portfolio_source_observation_migration_dependencies import (
    downgrade_observation_schema,
    observation_schema_semantics,
    restore_observation_schema,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.asyncio]


def receipt_schema_signature(engine):
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL search_path TO pg_temp"))
        observations = observation_schema_semantics(connection)
        constraints = tuple(
            tuple(row)
            for row in connection.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid), convalidated FROM pg_constraint "
                    "WHERE conrelid='public.portfolio_source_fact_verifications'::regclass "
                    "ORDER BY conname"
                )
            )
        )
        triggers = tuple(
            tuple(row)
            for row in connection.execute(
                text(
                    "SELECT tgname, tgenabled, pg_get_triggerdef(oid) FROM pg_trigger "
                    "WHERE tgrelid='public.portfolio_source_fact_verifications'::regclass "
                    "AND NOT tgisinternal ORDER BY tgname"
                )
            )
        )
        assert len(triggers) == 2 and all(row[1] == "O" for row in triggers)
        assert sum("FOREIGN KEY" in row[1] for row in constraints) == 2
        assert all(row[2] for row in constraints)
        return observations, constraints, triggers


@pytest.mark.parametrize("scope", ["function", "module"])
@pytest.mark.parametrize("populated", [False, True], ids=["empty", "populated"])
async def test_native_cleanup_recreates_complete_immutable_dependency(
    db_engine, clean_db, scope, populated
):
    before = receipt_schema_signature(db_engine)
    engine = create_async_database_engine(
        runtime_identity="lotus-core-test",
        database_url=db_engine.url.render_as_string(hide_password=False),
        pool_mode=DatabasePoolMode.NULL,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    identity = uuid4().hex
    lease = observation_proof.ObservationLease(
        sessions, "cleanup-" + identity, "portfolio-" + identity, "public"
    )
    try:
        if populated:
            async with sessions.begin() as session:
                session.add(
                    Portfolio(
                        portfolio_id=lease.portfolio,
                        tenant_id=lease.tenant,
                        legal_book_id="synthetic-book",
                        base_currency="SGD",
                        open_date=date(2020, 1, 1),
                        risk_exposure="MODERATE",
                        investment_time_horizon="LONG_TERM",
                        portfolio_type="DISCRETIONARY",
                        booking_center_code="SG",
                        client_id="synthetic-client",
                        status="ACTIVE",
                        is_leverage_allowed=False,
                    )
                )
            fact = lease.cash()
            authority, receipt, _ = verification_proof.registered(fact)
            await lease.create(
                fact, callback=verification_proof.stager(fact, authority, receipt).stage
            )
        # Ordinary mutation is still refused, including statement TRUNCATE when empty.
        operations = ["TRUNCATE public.portfolio_source_fact_verifications"]
        if populated:
            operations += [
                "UPDATE public.portfolio_source_fact_verifications SET consumer_id='other'",
                "DELETE FROM public.portfolio_source_fact_verifications",
            ]
        for sql in operations:
            with pytest.raises(DBAPIError, match="SOURCE_FACT_VERIFICATION_IMMUTABLE"):
                with db_engine.begin() as connection:
                    connection.execute(text(sql))
        fixture = harness.clean_db if scope == "function" else harness.clean_db_module
        if populated and scope == "function":
            with pytest.raises(DBAPIError, match="SOURCE_FACT_VERIFICATION_DOWNGRADE_NONEMPTY"):
                with db_engine.begin() as connection:
                    downgrade_observation_schema(connection)
            assert receipt_schema_signature(db_engine) == before
            authorization = authorize_database_cleanup(
                runtime=harness._test_runtime, engine=db_engine
            )
            view = "cleanup_dependency_" + identity
            require_database_cleanup_authorization(authorization, engine=db_engine)
            with db_engine.begin() as connection:
                connection.execute(
                    text(
                        f"CREATE VIEW public.{view} AS "
                        "SELECT attestation_sha256 FROM public.portfolio_source_fact_verifications"
                    )
                )
            try:
                with pytest.raises(DBAPIError, match="depend on it"):
                    next(fixture.__wrapped__(db_engine))
                # Unlisted dependency refuses DDL; prior receipt and guards survive rollback.
                assert receipt_schema_signature(db_engine) == before
                with db_engine.begin() as connection:
                    assert (
                        connection.scalar(
                            text("SELECT count(*) FROM public.portfolio_source_fact_verifications")
                        )
                        == 1
                    )
            finally:
                require_database_cleanup_authorization(authorization, engine=db_engine)
                with db_engine.begin() as connection:
                    connection.execute(text(f"DROP VIEW public.{view}"))
        reset = fixture.__wrapped__(db_engine)
        next(reset)
        with pytest.raises(StopIteration):
            next(reset)
        assert receipt_schema_signature(db_engine) == before
        with db_engine.begin() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM public.portfolio_source_fact_verifications")
                )
                == 0
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM public.portfolio_cash_availability_observations")
                )
                == 0
            )
        # A subsequent native function fixture sees complete, guarded schema too.
        following = harness.clean_db.__wrapped__(db_engine)
        next(following)
        with pytest.raises(StopIteration):
            next(following)
        assert receipt_schema_signature(db_engine) == before
        if not populated and scope == "module":
            with db_engine.begin() as connection:
                migration = downgrade_observation_schema(connection)
                assert (
                    connection.scalar(
                        text("SELECT to_regclass('public.portfolio_source_fact_verifications')")
                    )
                    is None
                )
                restore_observation_schema(migration, connection)
            assert receipt_schema_signature(db_engine) == before
        with pytest.raises(DBAPIError, match="SOURCE_FACT_VERIFICATION_IMMUTABLE"):
            with db_engine.begin() as connection:
                connection.execute(text("TRUNCATE public.portfolio_source_fact_verifications"))
    finally:
        await engine.dispose()
