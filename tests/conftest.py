# tests/conftest.py
import os
import sys
import time
from typing import Any, Callable

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, exc, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from tests.e2e.api_client import E2EApiClient
from tests.test_support.db_cleanup import truncate_with_deadlock_retry
from tests.test_support.docker_stack import (
    DockerStackError,
    compose_down,
    compose_up,
    resolve_compose_file,
    should_build_images,
    wait_for_http_health,
    wait_for_kafka_metadata,
    wait_for_migration_runner,
)
from tests.test_support.output_control import emit_test_output
from tests.test_support.pipeline_quiescence import (
    read_pipeline_activity_snapshot,
    read_pipeline_last_activity_at,
    wait_for_pipeline_quiescence,
)
from tests.test_support.runtime_env import build_test_runtime_env, infer_test_profile

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

_runtime_env, _runtime_endpoints = build_test_runtime_env(
    profile=os.getenv("LOTUS_TEST_ENV_PROFILE", infer_test_profile()),
    scope=os.getenv("LOTUS_TEST_SCOPE", "pytest"),
    preserve_existing=True,
)
os.environ.update(_runtime_env)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


DB_ONLY_SCOPES = {
    "unit-db",
    "transaction-buy-contract",
    "transaction-dividend-contract",
    "transaction-interest-contract",
    "transaction-fx-contract",
}

FULL_STACK_SERVICES = [
    "zookeeper",
    "kafka",
    "kafka-topic-creator",
    "postgres",
    "migration-runner",
    "ingestion_service",
    "event_replay_service",
    "financial_reconciliation_service",
    "query_service",
    "query_control_plane_service",
    "persistence_service",
    "cost_calculator_service",
    "cashflow_calculator_service",
    "position_calculator_service",
    "pipeline_orchestrator_service",
    "position_valuation_calculator",
    "timeseries_generator_service",
    "valuation_orchestrator_service",
    "portfolio_aggregation_service",
]

DB_ONLY_SERVICES = [
    "postgres",
    "migration-runner",
]


def _test_services_for_scope(scope: str) -> list[str]:
    if scope in DB_ONLY_SCOPES:
        return list(DB_ONLY_SERVICES)
    return list(FULL_STACK_SERVICES)


# REFACTORED: Use subprocess directly for more control over Docker Compose
@pytest.fixture(scope="session")
def docker_services(request):  # noqa: ARG001
    """
    Starts the Docker Compose stack using subprocess and waits for services to be healthy.
    This provides more control and resilience than the default testcontainers behavior.
    """
    compose_file = resolve_compose_file(project_root)
    compose_retries = _env_int("LOTUS_TESTS_COMPOSE_UP_RETRIES", 3)
    compose_retry_wait = _env_int("LOTUS_TESTS_COMPOSE_RETRY_WAIT_SECONDS", 5)
    migrations_timeout = _env_int("LOTUS_TESTS_MIGRATION_TIMEOUT_SECONDS", 240)
    health_timeout = _env_int("LOTUS_TESTS_HEALTH_TIMEOUT_SECONDS", 180)

    try:
        emit_test_output(
            "\n--- Test runtime ---\n"
            f"project={os.environ['COMPOSE_PROJECT_NAME']}\n"
            f"profile={os.environ['LOTUS_TEST_ENV_PROFILE']}\n"
            f"db={os.environ['HOST_DATABASE_URL']}\n"
            f"ingestion={os.environ['E2E_INGESTION_URL']}\n"
            f"query={os.environ['E2E_QUERY_URL']}\n"
            f"query_control={os.environ['E2E_QUERY_CONTROL_PLANE_URL']}\n"
            f"event_replay={os.environ['E2E_EVENT_REPLAY_URL']}"
        )
        test_scope = os.environ["LOTUS_TEST_SCOPE"]
        test_services = _test_services_for_scope(test_scope)
        compose_up(
            compose_file,
            build=should_build_images(),
            services=test_services,
            retries=compose_retries,
            retry_wait_seconds=compose_retry_wait,
        )

        emit_test_output("\n--- Waiting for database migrations to complete ---")
        wait_for_migration_runner(
            compose_file,
            timeout_seconds=migrations_timeout,
            poll_seconds=2,
        )
        emit_test_output("--- Database migrations completed successfully ---")
        if "kafka" in test_services:
            wait_for_kafka_metadata(
                os.environ["KAFKA_BOOTSTRAP_SERVERS"],
                timeout_seconds=health_timeout,
                poll_seconds=2,
            )
            emit_test_output(
                f"--- Kafka is metadata-ready at {os.environ['KAFKA_BOOTSTRAP_SERVERS']} ---"
            )

        # Manual polling for service health
        health_targets = {
            "ingestion_service": os.environ["E2E_INGESTION_URL"].rstrip("/") + "/health/ready",
            "event_replay_service": os.environ["E2E_EVENT_REPLAY_URL"].rstrip("/")
            + "/health/ready",
            "financial_reconciliation_service": (
                f"http://localhost:{os.environ['LOTUS_FINANCIAL_RECONCILIATION_HOST_PORT']}"
                + "/health/ready"
            ),
            "query_service": os.environ["E2E_QUERY_URL"].rstrip("/") + "/health/ready",
            "query_control_plane_service": os.environ["E2E_QUERY_CONTROL_PLANE_URL"].rstrip("/")
            + "/health/ready",
            "valuation_orchestrator_service": (
                f"http://localhost:{os.environ['LOTUS_VALUATION_ORCHESTRATOR_HOST_PORT']}"
                + "/health/ready"
            ),
            "portfolio_aggregation_service": (
                f"http://localhost:{os.environ['LOTUS_PORTFOLIO_AGGREGATION_HOST_PORT']}"
                + "/health/ready"
            ),
        }
        services_to_check = {
            service_name: health_targets[service_name]
            for service_name in test_services
            if service_name in health_targets
        }

        if services_to_check:
            emit_test_output("\n--- Waiting for API services to become healthy ---")
            for service_name, health_url in services_to_check.items():
                wait_for_http_health(
                    service_name,
                    health_url,
                    timeout_seconds=health_timeout,
                    poll_seconds=3,
                )
                emit_test_output(
                    f"--- Service '{service_name}' is healthy at {health_url} ---",
                    verbose_only=True,
                )

            emit_test_output("\n--- All API services are healthy, proceeding with tests ---")
        yield
    except DockerStackError as exc:
        pytest.fail(str(exc))

    finally:
        if _env_bool("LOTUS_TESTS_KEEP_STACK_UP", False):
            emit_test_output(
                "\n--- Keeping Docker services running for post-failure inspection ---"
            )
        else:
            emit_test_output("\n--- Tearing down Docker services ---")
            compose_down(compose_file)


# --- NEW: E2E API Client Fixture ---
@pytest.fixture(scope="session")
def e2e_api_client(docker_services) -> E2EApiClient:
    """Provides an instance of the E2EApiClient for E2E tests."""
    return E2EApiClient(
        ingestion_url=os.environ["E2E_INGESTION_URL"],
        query_url=os.environ["E2E_QUERY_URL"],
        query_control_plane_url=os.environ["E2E_QUERY_CONTROL_PLANE_URL"],
    )


# --- END NEW ---


@pytest.fixture(scope="session")
def db_engine(docker_services):
    """
    Provides a SQLAlchemy Engine, ensuring the Docker services are running first.
    """
    db_url = os.getenv(
        "HOST_DATABASE_URL",
        _runtime_endpoints.host_database_url,
    )

    # Wait for the database to be connectable
    engine = create_engine(db_url, pool_pre_ping=True)
    timeout = _env_int("LOTUS_TESTS_DB_CONNECT_TIMEOUT_SECONDS", 120)
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            emit_test_output("--- Database is connectable ---", verbose_only=True)
            yield engine
            engine.dispose()
            return
        except exc.OperationalError:
            time.sleep(2)

    pytest.fail(f"Database did not become connectable within {timeout} seconds.")


# List of all tables to be cleaned. Centralized here.
TABLES_TO_TRUNCATE = [
    "instrument_reprocessing_state",  # <-- ADD NEW TABLE HERE
    "reprocessing_jobs",
    "accrued_income_offset_state",
    "position_lot_state",
    "position_state",
    "business_dates",
    "portfolio_valuation_jobs",
    "portfolio_aggregation_jobs",
    "transaction_costs",
    "cashflows",
    "position_history",
    "daily_position_snapshots",
    "position_timeseries",
    "portfolio_timeseries",
    "transactions",
    "market_prices",
    "instruments",
    "fx_rates",
    "portfolios",
    "processed_events",
    "outbox_events",
    "pipeline_stage_state",
    "financial_reconciliation_findings",
    "financial_reconciliation_runs",
]
TERMINATE_ACTIVE_SESSIONS_SQL = """
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND usename = current_user;
"""


def _build_truncate_sql(connection) -> str:
    """Builds a truncate statement only for tables that exist in the current schema."""
    existing_tables = {
        row[0]
        for row in connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).fetchall()
    }
    tables = [table for table in TABLES_TO_TRUNCATE if table in existing_tables]
    if not tables:
        return ""
    return f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE;"


def _wait_for_pipeline_idle(db_engine) -> None:
    timeout_seconds = _env_int("LOTUS_TESTS_QUIESCENCE_TIMEOUT_SECONDS", 120)
    poll_seconds = _env_int("LOTUS_TESTS_QUIESCENCE_POLL_SECONDS", 1)
    stable_cycles = _env_int("LOTUS_TESTS_QUIESCENCE_STABLE_CYCLES", 2)
    quiet_seconds = _env_int("LOTUS_TESTS_QUIESCENCE_QUIET_SECONDS", 8)
    wait_for_pipeline_quiescence(
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
        stable_cycles=stable_cycles,
        snapshot_reader=lambda: read_pipeline_activity_snapshot(db_engine),
        quiet_seconds=quiet_seconds,
        last_activity_reader=lambda: read_pipeline_last_activity_at(db_engine),
    )


@pytest.fixture(scope="function")
def clean_db(db_engine):
    """
    A function-scoped fixture that cleans all data from tables using TRUNCATE.
    """
    emit_test_output("\n--- Cleaning database tables (function scope) ---", verbose_only=True)
    terminate_sessions_query = text(TERMINATE_ACTIVE_SESSIONS_SQL)
    terminate_sessions = _env_bool("LOTUS_TESTS_TERMINATE_DB_SESSIONS", False)

    def _terminate_for_deadlock_retry() -> None:
        with db_engine.begin() as connection:
            connection.execute(terminate_sessions_query)
        db_engine.dispose()

    def _run() -> None:
        with db_engine.begin() as connection:
            if terminate_sessions:
                connection.execute(terminate_sessions_query)
            truncate_sql = _build_truncate_sql(connection)
            if truncate_sql:
                connection.execute(text(truncate_sql))

    truncate_with_deadlock_retry(
        _run,
        on_deadlock_retry=_terminate_for_deadlock_retry if not terminate_sessions else None,
    )
    yield


@pytest.fixture(scope="module")
def clean_db_module(db_engine):
    """
    A module-scoped fixture that cleans all data from tables using TRUNCATE.
    Used by E2E tests to ensure a clean state before the test module runs.
    """
    emit_test_output("\n--- Cleaning database tables (module scope) ---", verbose_only=True)
    terminate_sessions_query = text(TERMINATE_ACTIVE_SESSIONS_SQL)
    terminate_sessions = _env_bool("LOTUS_TESTS_TERMINATE_DB_SESSIONS", False)
    _wait_for_pipeline_idle(db_engine)

    def _terminate_for_deadlock_retry() -> None:
        with db_engine.begin() as connection:
            connection.execute(terminate_sessions_query)
        db_engine.dispose()

    def _run() -> None:
        with db_engine.begin() as connection:
            if terminate_sessions:
                connection.execute(terminate_sessions_query)
            truncate_sql = _build_truncate_sql(connection)
            if truncate_sql:
                connection.execute(text(truncate_sql))

    truncate_with_deadlock_retry(
        _run,
        on_deadlock_retry=_terminate_for_deadlock_retry if not terminate_sessions else None,
    )
    yield


@pytest_asyncio.fixture(scope="function")
async def async_db_session(db_engine):
    """
    A function-scoped async fixture that provides a SQLAlchemy AsyncSession.
    """
    sync_url = db_engine.url
    async_url = sync_url.render_as_string(hide_password=False).replace(
        "postgresql://", "postgresql+asyncpg://"
    )

    async_engine = create_async_engine(async_url)
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with AsyncSessionLocal() as session:
        yield session

    await async_engine.dispose()


@pytest.fixture(scope="module")
def poll_db_until(db_engine):
    """
    Provides a generic polling utility to query the database until a condition is met.
    """

    def _poll(
        query: str,
        validation_func: Callable[[Any], bool],
        params: dict = {},
        timeout: int = 60,
        interval: int = 2,
        fail_message: str = "DB Polling timed out.",
    ):
        start_time = time.time()
        last_result = None
        while time.time() - start_time < timeout:
            with Session(db_engine) as session:
                result = session.execute(text(query), params).fetchone()
                last_result = result
                if validation_func(result):
                    return result
            time.sleep(interval)

        pytest.fail(f"{fail_message} after {timeout} seconds. Last result: {last_result}")

    return _poll
