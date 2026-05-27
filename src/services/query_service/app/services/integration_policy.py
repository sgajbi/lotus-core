import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..dtos.integration_dto import EffectiveIntegrationPolicyResponse, PolicyProvenanceMetadata
from ..settings import load_query_service_settings

logger = logging.getLogger(__name__)

_CONSUMER_CANONICAL_MAP: dict[str, str] = {
    "LOTUS-MANAGE": "lotus-manage",
    "LOTUS-GATEWAY": "lotus-gateway",
    "UI": "UI",
}


@dataclass
class PolicyContext:
    policy_version: str
    policy_source: str
    matched_rule_id: str
    strict_mode: bool
    allowed_sections: list[str] | None
    warnings: list[str]


def canonical_consumer_system(value: str | None) -> str:
    raw = (value or "UNKNOWN").strip()
    if not raw:
        return "unknown"
    key = raw.upper()
    return _CONSUMER_CANONICAL_MAP.get(key, raw.lower())


def load_policy() -> dict[str, Any]:
    raw = load_query_service_settings().integration_snapshot_policy_json
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON; using defaults.")
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


def coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def normalize_sections(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    normalized: list[str] = []
    for item in raw:
        if isinstance(item, str):
            value = item.strip().upper()
            if value:
                normalized.append(value)
    return normalized


def resolve_consumer_sections(
    consumers: dict[str, Any] | None,
    consumer_system: str,
) -> tuple[list[str] | None, str | None]:
    if not isinstance(consumers, dict):
        return None, None
    canonical = canonical_consumer_system(consumer_system)
    for key, value in consumers.items():
        if canonical_consumer_system(str(key)) == canonical:
            return normalize_sections(value), str(key)
    return None, None


def resolve_policy_context(tenant_id: str, consumer_system: str) -> PolicyContext:
    policy = load_policy()

    strict_mode = coerce_bool(policy.get("strict_mode"), default=False)
    policy_source = "default"
    matched_rule_id = "default"
    warnings: list[str] = []

    allowed_sections, matched_consumer_key = resolve_consumer_sections(
        policy.get("consumers"),
        consumer_system,
    )
    if allowed_sections is not None:
        policy_source = "global"
        matched_rule_id = f"global.consumers.{matched_consumer_key}"

    tenants = policy.get("tenants")
    tenant_policy_raw = tenants.get(tenant_id) if isinstance(tenants, dict) else None
    if isinstance(tenant_policy_raw, dict):
        strict_mode = coerce_bool(tenant_policy_raw.get("strict_mode"), default=strict_mode)
        tenant_consumers = tenant_policy_raw.get("consumers")
        tenant_allowed, tenant_match_key = resolve_consumer_sections(
            tenant_consumers if isinstance(tenant_consumers, dict) else None,
            consumer_system,
        )
        if tenant_allowed is None:
            tenant_allowed = normalize_sections(tenant_policy_raw.get("default_sections"))
        if tenant_allowed is not None:
            allowed_sections = tenant_allowed
            policy_source = "tenant"
            if tenant_match_key is not None:
                matched_rule_id = f"tenant.{tenant_id}.consumers.{tenant_match_key}"
            else:
                matched_rule_id = f"tenant.{tenant_id}.default_sections"
        if "strict_mode" in tenant_policy_raw and matched_rule_id == "default":
            policy_source = "tenant"
            matched_rule_id = f"tenant.{tenant_id}.strict_mode"

    if allowed_sections is None:
        warnings.append("NO_ALLOWED_SECTION_RESTRICTION")

    return PolicyContext(
        policy_version=load_query_service_settings().lotus_core_policy_version,
        policy_source=policy_source,
        matched_rule_id=matched_rule_id,
        strict_mode=strict_mode,
        allowed_sections=allowed_sections,
        warnings=warnings,
    )


def build_effective_policy_response(
    *,
    consumer_system: str,
    tenant_id: str,
    include_sections: list[str] | None,
    generated_at: datetime | None = None,
) -> EffectiveIntegrationPolicyResponse:
    normalized_consumer = canonical_consumer_system(consumer_system)
    policy_context = resolve_policy_context(
        tenant_id=tenant_id,
        consumer_system=normalized_consumer,
    )

    if include_sections:
        requested = [section.upper() for section in include_sections]
        if policy_context.allowed_sections is None:
            allowed_sections = requested
        else:
            allowed_set = set(policy_context.allowed_sections)
            allowed_sections = [section for section in requested if section in allowed_set]
    elif policy_context.allowed_sections is not None:
        allowed_sections = policy_context.allowed_sections
    else:
        allowed_sections = []

    return EffectiveIntegrationPolicyResponse(
        consumer_system=normalized_consumer,
        tenant_id=tenant_id,
        generated_at=generated_at or datetime.now(UTC),
        policy_provenance=PolicyProvenanceMetadata(
            policy_version=policy_context.policy_version,
            policy_source=policy_context.policy_source,
            matched_rule_id=policy_context.matched_rule_id,
            strict_mode=policy_context.strict_mode,
        ),
        allowed_sections=allowed_sections,
        warnings=policy_context.warnings,
    )
