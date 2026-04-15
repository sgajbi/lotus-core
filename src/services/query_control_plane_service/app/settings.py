from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None else raw


def env_json_map(name: str) -> dict[str, Any]:
    raw = env_str(name, "{}")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


@dataclass(frozen=True, slots=True)
class QueryControlPlaneSettings:
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


def load_query_control_plane_settings() -> QueryControlPlaneSettings:
    return QueryControlPlaneSettings(
        enterprise_policy_version=env_str("ENTERPRISE_POLICY_VERSION", "1.0.0"),
        enterprise_enforce_authz=env_bool("ENTERPRISE_ENFORCE_AUTHZ", False),
        enterprise_enforce_read_authz=env_bool("ENTERPRISE_ENFORCE_READ_AUTHZ", False),
        enterprise_audit_reads=env_bool("ENTERPRISE_AUDIT_READS", False),
        enterprise_require_capability_rules=env_bool("ENTERPRISE_REQUIRE_CAPABILITY_RULES", False),
        enterprise_enforce_runtime_config=env_bool("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", False),
        enterprise_primary_key_id=env_str("ENTERPRISE_PRIMARY_KEY_ID", ""),
        enterprise_secret_rotation_days=env_int("ENTERPRISE_SECRET_ROTATION_DAYS", 90),
        enterprise_max_write_payload_bytes=env_int("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", 1_048_576),
        enterprise_feature_flags=env_json_map("ENTERPRISE_FEATURE_FLAGS_JSON"),
        enterprise_capability_rules=env_json_map("ENTERPRISE_CAPABILITY_RULES_JSON"),
    )
