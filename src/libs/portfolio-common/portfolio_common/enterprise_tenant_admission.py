"""Resolve required tenant authority at the shared enterprise HTTP boundary."""

from __future__ import annotations

from portfolio_common.domain.tenant import TenantContext, TenantId

TENANT_CONTEXT_REQUIRED_PROBLEM_TYPE = (
    "https://lotus.local/problems/enterprise/tenant-context-required"
)
TENANT_CONTEXT_REQUIRED_ERROR_CODE = "TENANT_CONTEXT_REQUIRED"


class TenantContextAdmissionError(ValueError):
    """Raised when a protected request has no attributable tenant authority."""


def resolve_enterprise_tenant_context(
    *,
    tenant_id: str | None,
    actor_id: str | None,
    role: str | None,
    service_identity: str | None,
    correlation_id: str | None,
    identity_verified: bool,
) -> TenantContext:
    """Build immutable request authority or fail before protected route execution."""

    try:
        resolved_tenant_id = TenantId(tenant_id or "")
    except (TypeError, ValueError) as exc:
        raise TenantContextAdmissionError("tenant_id is required") from exc

    return TenantContext(
        tenant_id=resolved_tenant_id,
        actor_id=actor_id,
        role=role,
        service_identity=service_identity,
        correlation_id=correlation_id,
        identity_verified=identity_verified,
    )


def tenant_context_required_problem(
    *,
    path: str,
    correlation_id: str | None,
) -> dict[str, object]:
    """Return the governed problem document for missing tenant authority."""

    return {
        "type": TENANT_CONTEXT_REQUIRED_PROBLEM_TYPE,
        "title": "Tenant Context Required",
        "status": 401,
        "detail": "A nonblank X-Tenant-Id header is required for this route.",
        "instance": path,
        "error_code": TENANT_CONTEXT_REQUIRED_ERROR_CODE,
        "correlation_id": correlation_id or "",
    }
