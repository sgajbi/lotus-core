"""Reusable tenant-admission dependencies for query-control HTTP contracts."""

from fastapi import Query, Request, status
from portfolio_common.domain.tenant import TenantAuthorityMismatchError, bind_tenant_authority

from .response_helpers import problem_example, problem_response, raise_problem


def require_admitted_tenant_query(
    request: Request,
    tenant_id: str = Query(
        ...,
        description="Source-owned tenant identifier; must match admitted tenant authority.",
        examples=["tenant_sg_pb"],
    ),
) -> str:
    """Return admitted tenant authority after rejecting a conflicting query scope."""

    try:
        return bind_tenant_authority(tenant_id, request.state.tenant_context)
    except (TenantAuthorityMismatchError, TypeError, ValueError):
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Tenant scope forbidden",
            detail="Requested tenant does not match admitted tenant authority.",
            error_code="QCP_TENANT_SCOPE_FORBIDDEN",
        )


def tenant_scope_forbidden_response() -> dict[str, object]:
    """Document the shared tenant-query authority failure contract."""

    return problem_response(
        "Requested tenant does not match admitted tenant authority.",
        problem_example(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Tenant scope forbidden",
            detail="Requested tenant does not match admitted tenant authority.",
            error_code="QCP_TENANT_SCOPE_FORBIDDEN",
        ),
    )
