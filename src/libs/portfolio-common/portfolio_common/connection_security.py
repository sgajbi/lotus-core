"""Fail-closed connection security policy shared by Core infrastructure adapters."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from portfolio_common.runtime_settings import (
    RuntimeConfigurationError,
    explicit_local_config_profile_enabled,
    runtime_environment_name,
)

DEFAULT_LOCAL_PASSWORDS = frozenset({"password"})


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
