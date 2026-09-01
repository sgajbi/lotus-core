"""Bind Query Control Plane requests to admitted tenant authority."""

from fastapi import status
from portfolio_common.domain.tenant import (
    TenantAuthorityMismatchError,
    TenantContext,
    bind_tenant_authority,
)

from .response_helpers import problem_example, raise_problem

TENANT_SCOPE_FORBIDDEN_EXAMPLE = problem_example(
    status_code=status.HTTP_403_FORBIDDEN,
    title="Tenant scope forbidden",
    detail="Requested tenant does not match admitted tenant authority.",
    error_code="QCP_TENANT_SCOPE_FORBIDDEN",
)


def require_matching_tenant_authority(
    *,
    supplied_tenant_id: str,
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
