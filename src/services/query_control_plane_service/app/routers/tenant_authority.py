"""HTTP-boundary tenant authority binding for query control-plane routes."""

from fastapi import status
from portfolio_common.domain.tenant import (
    TenantAuthorityMismatchError,
    TenantContext,
    bind_tenant_authority,
)

from .response_helpers import problem_example, raise_problem


def tenant_scope_forbidden_example(source_product: str) -> dict[str, object]:
    """Return route-accurate, source-safe OpenAPI evidence for tenant mismatch."""

    return problem_example(
        status_code=status.HTTP_403_FORBIDDEN,
        title="Tenant scope forbidden",
        detail="Requested tenant does not match admitted tenant authority.",
        error_code="QCP_TENANT_SCOPE_FORBIDDEN",
        metadata={"source_product": source_product},
    )


def bind_admitted_tenant_id(
    *,
    requested_tenant_id: str | None,
    tenant_context: TenantContext,
    source_product: str,
) -> str:
    """Return admitted tenant authority or fail closed without leaking tenant data."""

    try:
        return bind_tenant_authority(requested_tenant_id, tenant_context)
    except (TenantAuthorityMismatchError, ValueError):
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Tenant scope forbidden",
            detail="Requested tenant does not match admitted tenant authority.",
            error_code="QCP_TENANT_SCOPE_FORBIDDEN",
            metadata={"source_product": source_product},
        )
