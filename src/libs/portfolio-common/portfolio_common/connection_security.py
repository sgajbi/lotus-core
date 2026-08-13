"""Fail-closed connection security policy shared by Core infrastructure adapters."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from portfolio_common.runtime_settings import (
    RuntimeConfigurationError,
    explicit_local_config_profile_enabled,
    kafka_connection_security_settings,
    runtime_environment_name,
)

DEFAULT_LOCAL_PASSWORDS = frozenset({"password"})
KAFKA_SECURITY_PROTOCOLS = frozenset({"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"})
KAFKA_SASL_MECHANISMS = frozenset({"PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"})


def validate_database_url_security(database_url: str, *, service_name: str) -> None:
    """Reject absent or local-only database credentials outside an explicit local profile."""

    if explicit_local_config_profile_enabled():
        return

    parsed = urlsplit(database_url)
    password = unquote(parsed.password or "")
    if not password:
        raise _database_security_error(service_name, "database password is missing")
    if password.casefold() in DEFAULT_LOCAL_PASSWORDS:
        raise _database_security_error(
            service_name,
            "local default database credentials are not permitted",
        )


def _database_security_error(service_name: str, reason: str) -> RuntimeConfigurationError:
    environment = runtime_environment_name() or "unspecified"
    return RuntimeConfigurationError(
        f"Invalid {service_name} database security configuration for environment "
        f"'{environment}': {reason}. Supply the credential through the deployment secret store."
    )


def build_kafka_connection_config(
    bootstrap_servers: str,
    *,
    service_name: str,
) -> dict[str, object]:
    """Build one validated librdkafka connection configuration for every Core client."""

    settings = kafka_connection_security_settings()
    protocol = settings.security_protocol.strip().upper()
    if protocol not in KAFKA_SECURITY_PROTOCOLS:
        raise _kafka_security_error(service_name, "unsupported Kafka security protocol")
    if not explicit_local_config_profile_enabled() and protocol in {
        "PLAINTEXT",
        "SASL_PLAINTEXT",
    }:
        raise _kafka_security_error(
            service_name,
            "plaintext Kafka transport is permitted only in an explicit local/dev/test profile",
        )

    config: dict[str, object] = {
        "bootstrap.servers": bootstrap_servers,
        "security.protocol": protocol,
    }
    if protocol in {"SSL", "SASL_SSL"}:
        config["ssl.ca.location"] = _required_kafka_setting(
            "KAFKA_SSL_CA_LOCATION",
            settings.ssl_ca_location,
            service_name=service_name,
        )
    if protocol in {"SASL_PLAINTEXT", "SASL_SSL"}:
        mechanism = _required_kafka_setting(
            "KAFKA_SASL_MECHANISM",
            settings.sasl_mechanism,
            service_name=service_name,
        ).upper()
        if mechanism not in KAFKA_SASL_MECHANISMS:
            raise _kafka_security_error(service_name, "unsupported Kafka SASL mechanism")
        config.update(
            {
                "sasl.mechanism": mechanism,
                "sasl.username": _required_kafka_setting(
                    "KAFKA_SASL_USERNAME",
                    settings.sasl_username,
                    service_name=service_name,
                ),
                "sasl.password": _required_kafka_setting(
                    "KAFKA_SASL_PASSWORD",
                    settings.sasl_password,
                    service_name=service_name,
                ),
            }
        )
    return config


def _required_kafka_setting(name: str, value: str, *, service_name: str) -> str:
    value = value.strip()
    if not value:
        raise _kafka_security_error(service_name, f"required Kafka setting {name} is missing")
    return value


def _kafka_security_error(service_name: str, reason: str) -> RuntimeConfigurationError:
    environment = runtime_environment_name() or "unspecified"
    return RuntimeConfigurationError(
        f"Invalid {service_name} Kafka security configuration for environment "
        f"'{environment}': {reason}. Supply transport credentials and trust through the "
        "deployment secret store."
    )
