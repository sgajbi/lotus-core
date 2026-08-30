import json

import pytest
from portfolio_common.enterprise_tenant_admission import (
    TENANT_CONTEXT_REQUIRED_ERROR_CODE,
    TenantContextAdmissionError,
    resolve_enterprise_tenant_context,
    tenant_context_required_response,
)


def test_resolve_enterprise_tenant_context_preserves_verified_authority() -> None:
    context = resolve_enterprise_tenant_context(
        tenant_id=" tenant-a ",
        actor_id=" actor-1 ",
        role=" operator ",
        service_identity=" lotus-gateway ",
        correlation_id=" corr-1 ",
        identity_verified=True,
    )

    assert context.tenant_id_text == "tenant-a"
    assert context.actor_id == "actor-1"
    assert context.role == "operator"
    assert context.service_identity == "lotus-gateway"
    assert context.correlation_id == "corr-1"
    assert context.identity_verified is True


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_resolve_enterprise_tenant_context_rejects_missing_authority(
    tenant_id: str | None,
) -> None:
    with pytest.raises(TenantContextAdmissionError, match="tenant_id is required"):
        resolve_enterprise_tenant_context(
            tenant_id=tenant_id,
            actor_id=None,
            role=None,
            service_identity=None,
            correlation_id=None,
            identity_verified=False,
        )


def test_tenant_context_required_response_uses_governed_problem_contract() -> None:
    response = tenant_context_required_response(
        path="/api/v1/portfolios",
        correlation_id="corr-2",
    )

    assert response.status_code == 401
    assert response.media_type == "application/problem+json"
    assert json.loads(response.body) == {
        "type": "https://lotus.local/problems/enterprise/tenant-context-required",
        "title": "Tenant Context Required",
        "status": 401,
        "detail": "A nonblank X-Tenant-Id header is required for this route.",
        "instance": "/api/v1/portfolios",
        "error_code": TENANT_CONTEXT_REQUIRED_ERROR_CODE,
        "correlation_id": "corr-2",
    }
