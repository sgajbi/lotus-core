"""Always verify canonical source reads, including local middleware auth-bypass mode."""

from fastapi import Request, status
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.enterprise_readiness import (
    load_default_enterprise_settings,
    verify_service_principal,
)
from portfolio_common.enterprise_tenant_admission import (
    TenantContextAdmissionError,
    resolve_enterprise_tenant_context,
)

from .response_helpers import raise_problem


def verified_fx_source_context(request: Request) -> TenantContext:
    headers = dict(request.headers)
    principal = verify_service_principal(
        headers, load_default_enterprise_settings(service_name="query_control_plane_service")
    )
    context = None
    if not isinstance(principal, str):
        try:
            context = resolve_enterprise_tenant_context(
                tenant_id=headers.get("x-tenant-id"),
                actor_id=headers.get("x-actor-id"),
                role=headers.get("x-role"),
                service_identity=principal.service_identity,
                correlation_id=headers.get("x-correlation-id"),
                identity_verified=True,
            )
        except TenantContextAdmissionError:
            pass
    if context is None:
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Verified FX source scope required",
            detail="Retained FX selection requires verified tenant authority.",
            error_code="QCP_FX_SOURCE_SCOPE_FORBIDDEN",
        )
    return context
