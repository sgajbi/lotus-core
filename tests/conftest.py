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

# --- NEW: Import the E2E API Client ---
from tests.e2e.api_client import E2EApiClient
from tests.test_support.db_cleanup import truncate_with_deadlock_retry
from tests.test_support.docker_stack import (
    DockerStackError,
    compose_down,
    compose_up,
    resolve_compose_file,
    should_build_images,
    wait_for_http_health,
    wait_for_migration_runner,
)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Ensure host-routable DB defaults for any modules initialized during test import.
os.environ.setdefault("HOST_DATABASE_URL", "postgresql://user:password@localhost:55432/portfolio_db")
os.environ.setdefault("HOST_QUERY_DATABASE_URL", "postgresql://user:password@localhost:55432/portfolio_db")
# Keep demo ingestion sidecar disabled for deterministic integration/e2e tests.
os.environ.setdefault("DEMO_DATA_PACK_ENABLED", "false")


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
        test_services = [
            "zookeeper",
            "kafka",
            "kafka-topic-creator",
            "postgres",
            "migration-runner",
            "ingestion_service",
            "query_service",
            "persistence_service",
            "cost_calculator_service",
            "cashflow_calculator_service",
            "position_calculator_service",
            "position_valuation_calculator",
            "timeseries_generator_service",
        ]
        compose_up(
            compose_file,
            build=should_build_images(),
            services=test_services,
            retries=compose_retries,
            retry_wait_seconds=compose_retry_wait,
        )

        print("\n--- Waiting for database migrations to complete ---")
        wait_for_migration_runner(
            compose_file,
            timeout_seconds=migrations_timeout,
            poll_seconds=2,
        )
        print("--- Database migrations completed successfully ---")

        # Manual polling for service health
        print("\n--- Waiting for API services to become healthy ---")
        ingestion_base_url = os.getenv("E2E_INGESTION_URL", "http://localhost:8200").rstrip("/")
        query_base_url = os.getenv("E2E_QUERY_URL", "http://localhost:8201").rstrip("/")
        services_to_check = {
            "ingestion_service": f"{ingestion_base_url}/health/ready",
            "query_service": f"{query_base_url}/health/ready",
        }

        for service_name, health_url in services_to_check.items():
            wait_for_http_health(
                service_name,
                health_url,
                timeout_seconds=health_timeout,
                poll_seconds=3,
            )
            print(f"--- Service '{service_name}' is healthy at {health_url} ---")

        print("\n--- All API services are healthy, proceeding with tests ---")
        yield
    except DockerStackError as exc:
        pytest.fail(str(exc))

    finally:
        print("\n--- Tearing down Docker services ---")
        compose_down(compose_file)


# --- NEW: E2E API Client Fixture ---
@pytest.fixture(scope="session")
def e2e_api_client(docker_services) -> E2EApiClient:
    """Provides an instance of the E2EApiClient for E2E tests."""
    return E2EApiClient(
        ingestion_url=os.getenv("E2E_INGESTION_URL", "http://localhost:8200"),
        query_url=os.getenv("E2E_QUERY_URL", "http://localhost:8201"),
    )


# --- END NEW ---


@pytest.fixture(scope="session")
def db_engine(docker_services):
    """
    Provides a SQLAlchemy Engine, ensuring the Docker services are running first.
    """
    db_url = os.getenv(
        "HOST_DATABASE_URL",
        "postgresql://user:password@localhost:55432/portfolio_db",
    )

    # Wait for the database to be connectable
    engine = create_engine(db_url, pool_pre_ping=True)
    timeout = _env_int("LOTUS_TESTS_DB_CONNECT_TIMEOUT_SECONDS", 120)
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("--- Database is connectable ---")
            yield engine
            engine.dispose()
            return
        except exc.OperationalError:
            time.sleep(2)

    pytest.fail(f"Database did not become connectable within {timeout} seconds.")


# List of all tables to be cleaned. Centralized here.
TABLES_TO_TRUNCATE = [
    "instrument_reprocessing_state",  # <-- ADD NEW TABLE HERE
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
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        ).fetchall()
    }
    tables = [table for table in TABLES_TO_TRUNCATE if table in existing_tables]
    if not tables:
        return ""
    return f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE;"


@pytest.fixture(scope="function")
def clean_db(db_engine):
    """
    A function-scoped fixture that cleans all data from tables using TRUNCATE.
    """
    print("\n--- Cleaning database tables (function scope) ---")
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
    print("\n--- Cleaning database tables (module scope) ---")
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
                    return
            time.sleep(interval)

        pytest.fail(f"{fail_message} after {timeout} seconds. Last result: {last_result}")

    return _poll
