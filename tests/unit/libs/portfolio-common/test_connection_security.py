from __future__ import annotations

import pytest
from portfolio_common.connection_security import (
    build_kafka_connection_config,
    validate_database_url_security,
)
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


def test_explicit_local_profile_allows_plaintext_kafka(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("KAFKA_SECURITY_PROTOCOL", raising=False)

    assert build_kafka_connection_config(
        "kafka:9093",
        service_name="test-service",
    ) == {
        "bootstrap.servers": "kafka:9093",
        "security.protocol": "PLAINTEXT",
    }


@pytest.mark.parametrize("environment", [None, "", "staging", "uat", "production", "custom"])
def test_non_local_profile_rejects_plaintext_kafka(monkeypatch, environment: str | None) -> None:
    if environment is None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")

    with pytest.raises(RuntimeConfigurationError, match="plaintext Kafka transport"):
        build_kafka_connection_config("kafka:9093", service_name="test-service")


def test_non_local_ssl_kafka_requires_explicit_trust_store(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SSL")
    monkeypatch.delenv("KAFKA_SSL_CA_LOCATION", raising=False)

    with pytest.raises(RuntimeConfigurationError, match="KAFKA_SSL_CA_LOCATION is missing"):
        build_kafka_connection_config("kafka:9093", service_name="test-service")


def test_non_local_ssl_kafka_accepts_explicit_trust_store(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SSL")
    monkeypatch.setenv("KAFKA_SSL_CA_LOCATION", "/run/secrets/kafka-ca.pem")

    assert build_kafka_connection_config(
        "kafka:9093",
        service_name="test-service",
    ) == {
        "bootstrap.servers": "kafka:9093",
        "security.protocol": "SSL",
        "ssl.ca.location": "/run/secrets/kafka-ca.pem",
    }


def test_sasl_ssl_kafka_requires_and_maps_secret_sourced_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setenv("KAFKA_SSL_CA_LOCATION", "/run/secrets/kafka-ca.pem")
    monkeypatch.setenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
    monkeypatch.setenv("KAFKA_SASL_USERNAME", "core-service")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD", "secret-value")

    assert build_kafka_connection_config(
        "kafka:9093",
        service_name="test-service",
    ) == {
        "bootstrap.servers": "kafka:9093",
        "security.protocol": "SASL_SSL",
        "ssl.ca.location": "/run/secrets/kafka-ca.pem",
        "sasl.mechanism": "SCRAM-SHA-512",
        "sasl.username": "core-service",
        "sasl.password": "secret-value",
    }


def test_sasl_ssl_kafka_preserves_credential_whitespace(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setenv("KAFKA_SSL_CA_LOCATION", "/run/secrets/kafka-ca.pem")
    monkeypatch.setenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
    monkeypatch.setenv("KAFKA_SASL_USERNAME", " core-service ")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD", " secret-value ")

    config = build_kafka_connection_config("kafka:9093", service_name="test-service")

    assert config["sasl.username"] == " core-service "
    assert config["sasl.password"] == " secret-value "


@pytest.mark.parametrize("name", ["KAFKA_SASL_USERNAME", "KAFKA_SASL_PASSWORD"])
def test_sasl_ssl_kafka_rejects_whitespace_only_credentials(monkeypatch, name: str) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setenv("KAFKA_SSL_CA_LOCATION", "/run/secrets/kafka-ca.pem")
    monkeypatch.setenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
    monkeypatch.setenv("KAFKA_SASL_USERNAME", "core-service")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD", "secret-value")
    monkeypatch.setenv(name, "   ")

    with pytest.raises(RuntimeConfigurationError, match=f"{name} is missing"):
        build_kafka_connection_config("kafka:9093", service_name="test-service")


def test_kafka_security_error_does_not_disclose_sasl_secret(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setenv("KAFKA_SSL_CA_LOCATION", "/run/secrets/kafka-ca.pem")
    monkeypatch.setenv("KAFKA_SASL_MECHANISM", "unsupported")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD", "private-secret")

    with pytest.raises(RuntimeConfigurationError) as exc_info:
        build_kafka_connection_config("private-kafka:9093", service_name="test-service")

    message = str(exc_info.value)
    assert "private-secret" not in message
    assert "private-kafka" not in message
