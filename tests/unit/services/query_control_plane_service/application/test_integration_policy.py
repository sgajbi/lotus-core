"""Behavior tests for QCP-owned effective integration policy resolution."""

from datetime import UTC, datetime

import pytest

from src.services.query_control_plane_service.app.application.integration_policy import (
    IntegrationPolicyConfiguration,
    IntegrationPolicyService,
    canonical_consumer_system,
    decode_policy,
    normalize_sections,
    resolve_consumer_sections,
    resolve_policy_context,
)


class _FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def utc_now(self) -> datetime:
        return self._value


def _service(*, policy_json: str = "", policy_version: str = "tenant-default-v1"):
    return IntegrationPolicyService(
        configuration=IntegrationPolicyConfiguration(
            policy_version=policy_version,
            policy_json=policy_json,
        ),
        clock=_FixedClock(datetime(2026, 2, 27, 9, 30, tzinfo=UTC)),
    )


def test_consumer_and_section_normalization_is_deterministic() -> None:
    assert canonical_consumer_system("lotus-manage") == "lotus-manage"
    assert canonical_consumer_system("UI") == "UI"
    assert canonical_consumer_system("Custom-System") == "custom-system"
    assert canonical_consumer_system(None) == "unknown"
    assert normalize_sections([" overview ", "HOLDINGS", "", 123]) == [
        "OVERVIEW",
        "HOLDINGS",
    ]
    assert resolve_consumer_sections({"LOTUS-MANAGE": ["overview"]}, "lotus-manage") == (
        ["OVERVIEW"],
        "LOTUS-MANAGE",
    )


@pytest.mark.parametrize("raw", ["", "not-json", '["not-a-policy-map"]'])
def test_decode_policy_falls_back_to_empty_policy(raw: str) -> None:
    assert decode_policy(raw) == {}


def test_policy_context_applies_global_then_tenant_precedence() -> None:
    policy = decode_policy(
        '{"strict_mode":false,'
        '"consumers":{"lotus-manage":["OVERVIEW","HOLDINGS"]},'
        '"tenants":{"tenant-a":{"strict_mode":true,'
        '"consumers":{"lotus-manage":["ALLOCATION"]}}}}'
    )

    global_context = resolve_policy_context(
        tenant_id="default",
        consumer_system="lotus-manage",
        policy=policy,
        policy_version="tenant-v7",
    )
    tenant_context = resolve_policy_context(
        tenant_id="tenant-a",
        consumer_system="lotus-manage",
        policy=policy,
        policy_version="tenant-v7",
    )

    assert global_context.policy_source == "global"
    assert global_context.allowed_sections == ["OVERVIEW", "HOLDINGS"]
    assert tenant_context.policy_version == "tenant-v7"
    assert tenant_context.policy_source == "tenant"
    assert tenant_context.matched_rule_id == "tenant.tenant-a.consumers.lotus-manage"
    assert tenant_context.strict_mode is True
    assert tenant_context.allowed_sections == ["ALLOCATION"]


def test_policy_context_preserves_tenant_consumer_provenance_on_default_fallback() -> None:
    policy = decode_policy(
        '{"tenants":{"tenant-x":{"strict_mode":true,'
        '"default_sections":["OVERVIEW"],'
        '"consumers":{"lotus-manage":null}}}}'
    )

    context = resolve_policy_context(
        tenant_id="tenant-x",
        consumer_system="lotus-manage",
        policy=policy,
        policy_version="v1",
    )

    assert context.matched_rule_id == "tenant.tenant-x.consumers.lotus-manage"
    assert context.allowed_sections == ["OVERVIEW"]
    assert context.strict_mode is True


def test_policy_service_filters_sections_and_uses_injected_clock() -> None:
    service = _service(
        policy_json='{"consumers":{"lotus-manage":["OVERVIEW","HOLDINGS"]}}',
        policy_version="tenant-v7",
    )

    response = service.get_effective_policy(
        consumer_system="LOTUS-MANAGE",
        tenant_id="default",
        include_sections=[" overview ", "allocation", " holdings "],
    )

    assert response.consumer_system == "lotus-manage"
    assert response.generated_at == datetime(2026, 2, 27, 9, 30, tzinfo=UTC)
    assert response.allowed_sections == ["OVERVIEW", "HOLDINGS"]
    assert response.policy_provenance.policy_version == "tenant-v7"
    assert response.policy_provenance.matched_rule_id == "global.consumers.lotus-manage"


def test_policy_service_passes_requested_sections_when_policy_is_unrestricted() -> None:
    response = _service().get_effective_policy(
        consumer_system="custom-client",
        tenant_id="default",
        include_sections=["overview", "allocation"],
    )

    assert response.allowed_sections == ["OVERVIEW", "ALLOCATION"]
    assert response.warnings == ["NO_ALLOWED_SECTION_RESTRICTION"]
