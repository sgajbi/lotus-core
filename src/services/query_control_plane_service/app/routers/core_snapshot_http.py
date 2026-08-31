"""HTTP-boundary helpers for the governed core-snapshot product."""

from typing import cast

from fastapi import status
from fastapi.encoders import jsonable_encoder
from portfolio_common.domain.tenant import (
    TenantAuthorityMismatchError,
    TenantContext,
    bind_tenant_authority,
)

from ..contracts.core_snapshot import CoreSnapshotRequest, CoreSnapshotResponse
from .response_helpers import raise_problem


def bind_core_snapshot_tenant_authority(
    request: CoreSnapshotRequest,
    tenant_context: TenantContext,
) -> CoreSnapshotRequest:
    """Replace caller scope with admitted authority or reject a conflict."""

    try:
        tenant_id = bind_tenant_authority(request.tenant_id, tenant_context)
    except (TenantAuthorityMismatchError, TypeError, ValueError):
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Core snapshot tenant scope forbidden",
            detail="Requested tenant does not match admitted tenant authority.",
            error_code="QCP_CORE_SNAPSHOT_TENANT_FORBIDDEN",
            metadata={"source_product": "PortfolioStateSnapshot"},
        )
    return request.model_copy(update={"tenant_id": tenant_id})


def lotus_idea_core_snapshot_payload(response: CoreSnapshotResponse | dict) -> dict:
    """Render the compatibility shape owned by the lotus-idea integration."""

    payload = cast(
        dict,
        jsonable_encoder(
            response.model_dump(mode="json")
            if isinstance(response, CoreSnapshotResponse)
            else response
        ),
    )
    payload["freshness_metadata"] = payload.get("freshness")
    payload["freshness"] = payload.get("freshness_status", "UNAVAILABLE")
    return payload
