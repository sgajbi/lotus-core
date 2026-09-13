"""Bind Query Control Plane requests to admitted tenant authority."""

from fastapi import Request, status
from portfolio_common.domain.tenant import (
    TenantAuthorityMismatchError,
    TenantContext,
    TenantId,
    bind_tenant_authority,
)

from .response_helpers import problem_example, problem_response, raise_problem

TENANT_SCOPE_FORBIDDEN_EXAMPLE = problem_example(
    status_code=status.HTTP_403_FORBIDDEN,
    title="Tenant scope forbidden",
    detail="Requested tenant does not match admitted tenant authority.",
    error_code="QCP_TENANT_SCOPE_FORBIDDEN",
)
TENANT_SCOPE_FORBIDDEN_RESPONSE = {
    status.HTTP_403_FORBIDDEN: problem_response(
        "Requested tenant does not match admitted tenant authority.",
        TENANT_SCOPE_FORBIDDEN_EXAMPLE,
    )
}


def require_matching_tenant_authority(
    *,
    supplied_tenant_id: str | None,
    tenant_context: TenantContext,
) -> str:
    """Return canonical admitted scope after rejecting caller-controlled mismatch."""

    try:
        return bind_tenant_authority(supplied_tenant_id, tenant_context)
    except (TenantAuthorityMismatchError, TypeError, ValueError):
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Tenant scope forbidden",
            detail="Requested tenant does not match admitted tenant authority.",
            error_code="QCP_TENANT_SCOPE_FORBIDDEN",
        )


def require_admitted_tenant_id(*, request: Request, supplied_tenant_id: str | None) -> TenantId:
    """Return typed admitted authority after rejecting a caller-controlled mismatch."""

    return TenantId(
        require_matching_tenant_authority(
            supplied_tenant_id=supplied_tenant_id,
            tenant_context=request.state.tenant_context,
        )
    )
