from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from portfolio_common.runtime_settings import (
    RuntimeConfigurationError,
    production_security_profile_enabled,
    strict_config_validation_enabled,
)
from portfolio_common.runtime_settings import env_bool as shared_env_bool
from portfolio_common.runtime_settings import env_int as shared_env_int
from portfolio_common.runtime_settings import env_json_map as shared_env_json_map
from portfolio_common.runtime_settings import env_str as shared_env_str

QUERY_SERVICE_NAME = "query service"
DEFAULT_PAGE_TOKEN_SECRET = "lotus-core-local-dev"
DEFAULT_PAGE_TOKEN_KEY_ID = "local-dev"


def env_bool(name: str, default: bool) -> bool:
    return shared_env_bool(name, default, service_name=QUERY_SERVICE_NAME)


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    minimum_fallback: int | None = None,
) -> int:
    return shared_env_int(
        name,
        default,
        service_name=QUERY_SERVICE_NAME,
        minimum=minimum,
        maximum=maximum,
        minimum_fallback=minimum_fallback,
    )


def env_str(name: str, default: str) -> str:
    return shared_env_str(name, default)


def env_json_map(name: str) -> dict[str, Any]:
    return shared_env_json_map(name, service_name=QUERY_SERVICE_NAME)


@dataclass(frozen=True, slots=True)
class QueryServiceSettings:
    lotus_core_policy_version: str
    integration_snapshot_policy_json: str
    capability_tenant_overrides_json: str
    page_token_secret: str
    page_token_key_id: str
    page_token_previous_keys: dict[str, str]
    page_token_ttl_seconds: int
    analytics_export_stale_timeout_minutes: int
    analytics_export_execution_timeout_seconds: int
    has_database_url: bool
    enterprise_policy_version: str
    enterprise_enforce_authz: bool
    enterprise_enforce_read_authz: bool
    enterprise_audit_reads: bool
    enterprise_require_capability_rules: bool
    enterprise_enforce_runtime_config: bool
    enterprise_primary_key_id: str
    enterprise_secret_rotation_days: int
    enterprise_max_write_payload_bytes: int
    enterprise_feature_flags: dict[str, Any]
    enterprise_capability_rules: dict[str, Any]


def load_query_service_settings() -> QueryServiceSettings:
    production_security_profile = production_security_profile_enabled(
        service_name=QUERY_SERVICE_NAME
    )
    return QueryServiceSettings(
        lotus_core_policy_version=env_str("LOTUS_CORE_POLICY_VERSION", "tenant-default-v1"),
        integration_snapshot_policy_json=env_str("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", ""),
        capability_tenant_overrides_json=env_str("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", ""),
        page_token_secret=_page_token_secret(),
        page_token_key_id=_page_token_key_id(),
        page_token_previous_keys=_page_token_previous_keys(),
        page_token_ttl_seconds=env_int("LOTUS_CORE_PAGE_TOKEN_TTL_SECONDS", 900, minimum=60),
        analytics_export_stale_timeout_minutes=env_int(
            "LOTUS_CORE_ANALYTICS_EXPORT_STALE_TIMEOUT_MINUTES", 15, minimum=1
        ),
        analytics_export_execution_timeout_seconds=env_int(
            "LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS", 300, minimum=1
        ),
        has_database_url=bool(os.getenv("HOST_DATABASE_URL") or os.getenv("DATABASE_URL")),
        enterprise_policy_version=env_str("ENTERPRISE_POLICY_VERSION", "1.0.0"),
        enterprise_enforce_authz=env_bool("ENTERPRISE_ENFORCE_AUTHZ", production_security_profile),
        enterprise_enforce_read_authz=env_bool(
            "ENTERPRISE_ENFORCE_READ_AUTHZ", production_security_profile
        ),
        enterprise_audit_reads=env_bool("ENTERPRISE_AUDIT_READS", production_security_profile),
        enterprise_require_capability_rules=env_bool(
            "ENTERPRISE_REQUIRE_CAPABILITY_RULES", production_security_profile
        ),
        enterprise_enforce_runtime_config=env_bool(
            "ENTERPRISE_ENFORCE_RUNTIME_CONFIG", production_security_profile
        ),
        enterprise_primary_key_id=env_str("ENTERPRISE_PRIMARY_KEY_ID", ""),
        enterprise_secret_rotation_days=env_int("ENTERPRISE_SECRET_ROTATION_DAYS", 90, minimum=1),
        enterprise_max_write_payload_bytes=env_int(
            "ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES",
            1_048_576,
            minimum=1,
            minimum_fallback=0,
        ),
        enterprise_feature_flags=env_json_map("ENTERPRISE_FEATURE_FLAGS_JSON"),
        enterprise_capability_rules=env_json_map("ENTERPRISE_CAPABILITY_RULES_JSON"),
    )


QueryServiceConfigurationError = RuntimeConfigurationError


def _page_token_secret() -> str:
    secret = env_str("LOTUS_CORE_PAGE_TOKEN_SECRET", DEFAULT_PAGE_TOKEN_SECRET).strip()
    if strict_config_validation_enabled() and (not secret or secret == DEFAULT_PAGE_TOKEN_SECRET):
        raise QueryServiceConfigurationError(
            "Invalid query service configuration for LOTUS_CORE_PAGE_TOKEN_SECRET: "
            "non-local profiles require a non-default page-token secret"
        )
    return secret


def _page_token_key_id() -> str:
    key_id = env_str("LOTUS_CORE_PAGE_TOKEN_KEY_ID", DEFAULT_PAGE_TOKEN_KEY_ID).strip()
    if strict_config_validation_enabled() and (not key_id or key_id == DEFAULT_PAGE_TOKEN_KEY_ID):
        raise QueryServiceConfigurationError(
            "Invalid query service configuration for LOTUS_CORE_PAGE_TOKEN_KEY_ID: "
            "non-local profiles require a non-default page-token key id"
        )
    return key_id


def _page_token_previous_keys() -> dict[str, str]:
    decoded = env_json_map("LOTUS_CORE_PAGE_TOKEN_PREVIOUS_KEYS_JSON")
    previous_keys: dict[str, str] = {}
    for key_id, secret in decoded.items():
        if not isinstance(key_id, str) or not key_id.strip():
            if strict_config_validation_enabled():
                raise QueryServiceConfigurationError(
                    "Invalid query service configuration for "
                    "LOTUS_CORE_PAGE_TOKEN_PREVIOUS_KEYS_JSON: key ids must be non-empty strings"
                )
            continue
        if not isinstance(secret, str) or not secret.strip():
            if strict_config_validation_enabled():
                raise QueryServiceConfigurationError(
                    "Invalid query service configuration for "
                    "LOTUS_CORE_PAGE_TOKEN_PREVIOUS_KEYS_JSON: secrets must be non-empty strings"
                )
            continue
        previous_keys[key_id] = secret
    return previous_keys
