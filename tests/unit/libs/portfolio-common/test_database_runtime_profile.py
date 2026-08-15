from __future__ import annotations

import logging

import pytest
from portfolio_common.database_runtime_identity import DATABASE_RUNTIME_IDENTITIES
from portfolio_common.database_runtime_profile import (
    DATABASE_CONNECT_TIMEOUT_SECONDS_ENV,
    DATABASE_IDLE_TRANSACTION_TIMEOUT_MS_ENV,
    DATABASE_MAX_OVERFLOW_ENV,
    DATABASE_POOL_RECYCLE_SECONDS_ENV,
    DATABASE_POOL_SIZE_ENV,
    DATABASE_POOL_TIMEOUT_SECONDS_ENV,
    DATABASE_RUNTIME_COHORT_BY_IDENTITY,
    DATABASE_STATEMENT_TIMEOUT_MS_ENV,
    DatabasePoolMode,
    DatabaseRuntimeProfileError,
    async_database_engine_options,
    database_runtime_profile,
    log_database_runtime_profile,
    sync_database_engine_options,
)
from sqlalchemy.pool import NullPool


def test_every_runtime_identity_has_exactly_one_owned_profile() -> None:
    assert set(DATABASE_RUNTIME_COHORT_BY_IDENTITY) == set(DATABASE_RUNTIME_IDENTITIES)


def test_queue_profile_makes_existing_effective_defaults_explicit(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "query-service")

    profile = database_runtime_profile()

    assert profile.pool_size == 5
    assert profile.max_overflow == 10
    assert profile.maximum_connections_per_process == 15
    assert profile.pool_timeout_seconds == 30
    assert profile.pool_recycle_seconds == -1
    assert profile.connect_timeout_seconds == 60
    assert profile.statement_timeout_ms == 0
    assert profile.idle_in_transaction_session_timeout_ms == 0


def test_driver_options_apply_equivalent_governed_settings(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "portfolio-derived-state")
    monkeypatch.setenv(DATABASE_STATEMENT_TIMEOUT_MS_ENV, "2500")
    monkeypatch.setenv(DATABASE_IDLE_TRANSACTION_TIMEOUT_MS_ENV, "5000")
    profile = database_runtime_profile()

    sync_options = sync_database_engine_options(profile)
    async_options = async_database_engine_options(profile)

    assert sync_options["connect_args"] == {
        "application_name": "portfolio-derived-state",
        "connect_timeout": 60,
        "options": "-c statement_timeout=2500 -c idle_in_transaction_session_timeout=5000",
    }
    assert async_options["connect_args"] == {
        "timeout": 60,
        "server_settings": {
            "application_name": "portfolio-derived-state",
            "statement_timeout": "2500ms",
            "idle_in_transaction_session_timeout": "5000ms",
        },
    }
    for key, expected in {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": -1,
    }.items():
        assert sync_options[key] == expected
        assert async_options[key] == expected


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (DATABASE_POOL_SIZE_ENV, "0"),
        (DATABASE_MAX_OVERFLOW_ENV, "33"),
        (DATABASE_POOL_TIMEOUT_SECONDS_ENV, "0"),
        (DATABASE_POOL_RECYCLE_SECONDS_ENV, "59"),
        (DATABASE_CONNECT_TIMEOUT_SECONDS_ENV, "61"),
        (DATABASE_STATEMENT_TIMEOUT_MS_ENV, "99"),
        (DATABASE_IDLE_TRANSACTION_TIMEOUT_MS_ENV, "999"),
        (DATABASE_POOL_SIZE_ENV, "secret-invalid-value"),
    ],
)
def test_invalid_profile_values_fail_closed_without_disclosing_value(
    monkeypatch, name, value
) -> None:
    monkeypatch.setenv("SERVICE_NAME", "query-service")
    monkeypatch.setenv(name, value)

    with pytest.raises(DatabaseRuntimeProfileError) as exc_info:
        database_runtime_profile()

    assert exc_info.value.setting == name
    if value == "secret-invalid-value":
        assert value not in str(exc_info.value)


def test_combined_pool_capacity_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "query-service")
    monkeypatch.setenv(DATABASE_POOL_SIZE_ENV, "20")
    monkeypatch.setenv(DATABASE_MAX_OVERFLOW_ENV, "13")

    with pytest.raises(DatabaseRuntimeProfileError, match="must not exceed 32"):
        database_runtime_profile()


def test_nullpool_omits_queue_options(monkeypatch) -> None:
    profile = database_runtime_profile(
        explicit_identity="migration-runner",
        pool_mode=DatabasePoolMode.NULL,
    )

    options = sync_database_engine_options(profile)

    assert profile.maximum_connections_per_process is None
    assert options == {
        "connect_args": {
            "application_name": "migration-runner",
            "connect_timeout": 60,
            "options": "-c statement_timeout=0 -c idle_in_transaction_session_timeout=0",
        },
        "poolclass": NullPool,
    }


def test_nullpool_rejects_explicit_queue_setting(monkeypatch) -> None:
    monkeypatch.setenv(DATABASE_POOL_SIZE_ENV, "5")

    with pytest.raises(DatabaseRuntimeProfileError, match="incompatible with NullPool"):
        database_runtime_profile(
            explicit_identity="migration-runner",
            pool_mode=DatabasePoolMode.NULL,
        )


def test_startup_evidence_contains_only_bounded_non_secret_fields(monkeypatch, caplog) -> None:
    monkeypatch.setenv("SERVICE_NAME", "query-service")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://sensitive-user:sensitive-password@secret-host/db"
    )
    profile = database_runtime_profile()

    with caplog.at_level(logging.INFO):
        log_database_runtime_profile(profile, driver="psycopg2")

    record = caplog.records[-1]
    assert record.runtime_identity == "query-service"
    assert record.database_runtime_cohort == "online-http"
    assert record.database_maximum_connections_per_process == 15
    rendered = str(record.__dict__)
    assert "sensitive-user" not in rendered
    assert "sensitive-password" not in rendered
    assert "secret-host" not in rendered
