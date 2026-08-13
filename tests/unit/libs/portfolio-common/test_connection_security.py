from __future__ import annotations

import pytest
from portfolio_common.connection_security import validate_database_url_security
from portfolio_common.runtime_settings import RuntimeConfigurationError


@pytest.mark.parametrize("environment", ["local", "dev", "development", "test"])
def test_explicit_local_profile_allows_local_database_password(
    monkeypatch, environment: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)

    validate_database_url_security(
        "postgresql://user:password@postgres:5432/portfolio_db",
        service_name="test-service",
    )


@pytest.mark.parametrize("environment", [None, "", "staging", "uat", "production", "custom"])
def test_non_local_profile_rejects_local_database_password(
    monkeypatch, environment: str | None
) -> None:
    if environment is None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT", environment)

    with pytest.raises(
        RuntimeConfigurationError,
        match="local default database credentials are not permitted",
    ):
        validate_database_url_security(
            "postgresql://user:password@postgres:5432/portfolio_db",
            service_name="test-service",
        )


def test_non_local_profile_rejects_encoded_local_database_password(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")

    with pytest.raises(RuntimeConfigurationError, match="local default database credentials"):
        validate_database_url_security(
            "postgresql://user:%70assword@postgres:5432/portfolio_db",
            service_name="test-service",
        )


def test_non_local_profile_rejects_missing_database_password(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeConfigurationError, match="database password is missing"):
        validate_database_url_security(
            "postgresql://user@postgres:5432/portfolio_db",
            service_name="test-service",
        )


def test_non_local_profile_accepts_secret_sourced_database_password(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    validate_database_url_security(
        "postgresql://service:governed-secret@postgres:5432/portfolio_db",
        service_name="test-service",
    )


def test_database_security_error_does_not_disclose_connection_url(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    database_url = "postgresql://private-user:password@private-host:5432/private-db"

    with pytest.raises(RuntimeConfigurationError) as exc_info:
        validate_database_url_security(database_url, service_name="test-service")

    message = str(exc_info.value)
    assert database_url not in message
    assert "private-user" not in message
    assert "private-host" not in message
