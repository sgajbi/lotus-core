"""HTTP-boundary tenant authority binding for query control-plane routes."""

from typing import TypeVar

from fastapi import status
from portfolio_common.domain.tenant import (
    TenantAuthorityMismatchError,
    TenantContext,
    bind_tenant_authority,
)
from pydantic import BaseModel

from .response_helpers import problem_example, problem_response, raise_problem

TenantRequestT = TypeVar("TenantRequestT", bound=BaseModel)


def tenant_scope_forbidden_example(source_product: str) -> dict[str, object]:
    """Return route-accurate, source-safe OpenAPI evidence for tenant mismatch."""

    return problem_example(
        status_code=status.HTTP_403_FORBIDDEN,
        title="Tenant scope forbidden",
        detail="Requested tenant does not match admitted tenant authority.",
        error_code="QCP_TENANT_SCOPE_FORBIDDEN",
        metadata={"source_product": source_product},
    )


def tenant_scope_forbidden_response(source_product: str) -> dict[str, object]:
    """Return the standard tenant-mismatch OpenAPI response contract."""

    return problem_response(
        "Requested tenant does not match admitted tenant authority.",
        tenant_scope_forbidden_example(source_product),
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


def bind_admitted_tenant_request(
    request: TenantRequestT,
    tenant_context: TenantContext,
    source_product: str,
) -> TenantRequestT:
    """Copy a request with caller-supplied tenant scope replaced by admitted authority."""

    if "tenant_id" not in type(request).model_fields:
        raise TypeError("tenant-bound requests must declare a tenant_id field")
    requested_tenant_id = request.model_dump(include={"tenant_id"}).get("tenant_id")
    if requested_tenant_id is not None and not isinstance(requested_tenant_id, str):
        raise TypeError("tenant_id must be a string when provided")
    return request.model_copy(
        update={
            "tenant_id": bind_admitted_tenant_id(
                requested_tenant_id=requested_tenant_id,
                tenant_context=tenant_context,
                source_product=source_product,
            )
        }
    )
