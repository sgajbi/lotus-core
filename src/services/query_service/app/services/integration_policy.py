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


def _default_policy_context(policy: dict[str, Any]) -> PolicyContext:
    return PolicyContext(
        policy_version=load_query_service_settings().lotus_core_policy_version,
        policy_source="default",
        matched_rule_id="default",
        strict_mode=coerce_bool(policy.get("strict_mode"), default=False),
        allowed_sections=None,
        warnings=[],
    )


def _global_policy_context(
    *,
    policy: dict[str, Any],
    consumer_system: str,
    context: PolicyContext,
) -> PolicyContext:
    allowed_sections, matched_consumer_key = resolve_consumer_sections(
        policy.get("consumers"),
        consumer_system,
    )
    if allowed_sections is None:
        return context
    return PolicyContext(
        policy_version=context.policy_version,
        policy_source="global",
        matched_rule_id=f"global.consumers.{matched_consumer_key}",
        strict_mode=context.strict_mode,
        allowed_sections=allowed_sections,
        warnings=context.warnings,
    )


def _tenant_policy(policy: dict[str, Any], tenant_id: str) -> dict[str, Any] | None:
    tenants = policy.get("tenants")
    tenant_policy_raw = tenants.get(tenant_id) if isinstance(tenants, dict) else None
    return tenant_policy_raw if isinstance(tenant_policy_raw, dict) else None


def _tenant_allowed_sections(
    *,
    tenant_policy: dict[str, Any],
    consumer_system: str,
) -> tuple[list[str] | None, str | None]:
    tenant_consumers = tenant_policy.get("consumers")
    tenant_allowed, tenant_match_key = resolve_consumer_sections(
        tenant_consumers if isinstance(tenant_consumers, dict) else None,
        consumer_system,
    )
    if tenant_allowed is not None:
        return tenant_allowed, tenant_match_key
    return normalize_sections(tenant_policy.get("default_sections")), None


def _tenant_matched_rule_id(
    *,
    tenant_id: str,
    tenant_match_key: str | None,
) -> str:
    if tenant_match_key is not None:
        return f"tenant.{tenant_id}.consumers.{tenant_match_key}"
    return f"tenant.{tenant_id}.default_sections"


def _tenant_policy_context(
    *,
    tenant_id: str,
    consumer_system: str,
    tenant_policy: dict[str, Any],
    context: PolicyContext,
) -> PolicyContext:
    strict_mode = coerce_bool(tenant_policy.get("strict_mode"), default=context.strict_mode)
    tenant_allowed, tenant_match_key = _tenant_allowed_sections(
        tenant_policy=tenant_policy,
        consumer_system=consumer_system,
    )
    if tenant_allowed is not None:
        return PolicyContext(
            policy_version=context.policy_version,
            policy_source="tenant",
            matched_rule_id=_tenant_matched_rule_id(
                tenant_id=tenant_id,
                tenant_match_key=tenant_match_key,
            ),
            strict_mode=strict_mode,
            allowed_sections=tenant_allowed,
            warnings=context.warnings,
        )
    if "strict_mode" in tenant_policy and context.matched_rule_id == "default":
        return PolicyContext(
            policy_version=context.policy_version,
            policy_source="tenant",
            matched_rule_id=f"tenant.{tenant_id}.strict_mode",
            strict_mode=strict_mode,
            allowed_sections=context.allowed_sections,
            warnings=context.warnings,
        )
    return PolicyContext(
        policy_version=context.policy_version,
        policy_source=context.policy_source,
        matched_rule_id=context.matched_rule_id,
        strict_mode=strict_mode,
        allowed_sections=context.allowed_sections,
        warnings=context.warnings,
    )


def _with_allowed_section_warning(context: PolicyContext) -> PolicyContext:
    if context.allowed_sections is not None:
        return context
    return PolicyContext(
        policy_version=context.policy_version,
        policy_source=context.policy_source,
        matched_rule_id=context.matched_rule_id,
        strict_mode=context.strict_mode,
        allowed_sections=context.allowed_sections,
        warnings=[*context.warnings, "NO_ALLOWED_SECTION_RESTRICTION"],
    )


def resolve_policy_context(tenant_id: str, consumer_system: str) -> PolicyContext:
    policy = load_policy()
    context = _global_policy_context(
        policy=policy,
        consumer_system=consumer_system,
        context=_default_policy_context(policy),
    )
    tenant_policy = _tenant_policy(policy, tenant_id)
    if tenant_policy is not None:
        context = _tenant_policy_context(
            tenant_id=tenant_id,
            consumer_system=consumer_system,
            tenant_policy=tenant_policy,
            context=context,
        )
    return _with_allowed_section_warning(context)


def resolve_effective_policy_response(
    *,
    consumer_system: str,
    tenant_id: str,
    include_sections: list[str] | None,
) -> EffectiveIntegrationPolicyResponse:
    return build_effective_policy_response(
        consumer_system=consumer_system,
        tenant_id=tenant_id,
        include_sections=include_sections,
        generated_at=datetime.now(UTC),
    )


def _effective_allowed_sections(
    *,
    requested_sections: list[str] | None,
    policy_allowed_sections: list[str] | None,
) -> list[str]:
    if requested_sections:
        return _requested_allowed_sections(
            requested_sections=requested_sections,
            policy_allowed_sections=policy_allowed_sections,
        )
    if policy_allowed_sections is not None:
        return policy_allowed_sections
    return []


def _requested_allowed_sections(
    *,
    requested_sections: list[str],
    policy_allowed_sections: list[str] | None,
) -> list[str]:
    requested = normalize_sections(requested_sections) or []
    if policy_allowed_sections is None:
        return requested
    allowed_set = set(policy_allowed_sections)
    return [section for section in requested if section in allowed_set]


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
        allowed_sections=_effective_allowed_sections(
            requested_sections=include_sections,
            policy_allowed_sections=policy_context.allowed_sections,
        ),
        warnings=policy_context.warnings,
    )
