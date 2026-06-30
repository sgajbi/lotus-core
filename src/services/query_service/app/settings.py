from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from portfolio_common.runtime_settings import RuntimeConfigurationError
from portfolio_common.runtime_settings import env_bool as shared_env_bool
from portfolio_common.runtime_settings import env_int as shared_env_int
from portfolio_common.runtime_settings import env_json_map as shared_env_json_map
from portfolio_common.runtime_settings import env_str as shared_env_str

QUERY_SERVICE_NAME = "query service"


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
    analytics_export_stale_timeout_minutes: int
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
    return QueryServiceSettings(
        lotus_core_policy_version=env_str("LOTUS_CORE_POLICY_VERSION", "tenant-default-v1"),
        integration_snapshot_policy_json=env_str("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", ""),
        capability_tenant_overrides_json=env_str("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", ""),
        page_token_secret=env_str("LOTUS_CORE_PAGE_TOKEN_SECRET", "lotus-core-local-dev"),
        analytics_export_stale_timeout_minutes=env_int(
            "LOTUS_CORE_ANALYTICS_EXPORT_STALE_TIMEOUT_MINUTES", 15, minimum=1
        ),
        has_database_url=bool(os.getenv("HOST_DATABASE_URL") or os.getenv("DATABASE_URL")),
        enterprise_policy_version=env_str("ENTERPRISE_POLICY_VERSION", "1.0.0"),
        enterprise_enforce_authz=env_bool("ENTERPRISE_ENFORCE_AUTHZ", False),
        enterprise_enforce_read_authz=env_bool("ENTERPRISE_ENFORCE_READ_AUTHZ", False),
        enterprise_audit_reads=env_bool("ENTERPRISE_AUDIT_READS", False),
        enterprise_require_capability_rules=env_bool("ENTERPRISE_REQUIRE_CAPABILITY_RULES", False),
        enterprise_enforce_runtime_config=env_bool("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", False),
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
