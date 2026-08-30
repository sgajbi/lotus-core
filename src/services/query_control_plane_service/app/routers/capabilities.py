from typing import cast

from fastapi import APIRouter, Depends, Query, Request

from ..application.capabilities_service import CapabilitiesService
from ..contracts.capabilities import (
    ConsumerSystem,
    IntegrationCapabilitiesResponse,
)
from ..infrastructure import SqlAlchemyBusinessDateProvider
from .response_helpers import problem_response
from .tenant_authority import bind_admitted_tenant_id, tenant_scope_forbidden_example

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])


def get_capabilities_service() -> CapabilitiesService:
    return CapabilitiesService(business_dates=SqlAlchemyBusinessDateProvider())


@router.get(
    "/capabilities",
    response_model=IntegrationCapabilitiesResponse,
    responses={
        403: problem_response(
            "Requested tenant does not match admitted tenant authority.",
            tenant_scope_forbidden_example("IntegrationCapabilities"),
        )
    },
    summary="Get lotus-core Integration Capabilities",
    description=(
        "What: Return policy-resolved integration capabilities for a consumer and tenant context.\n"
        "How: Applies environment and tenant-policy overrides, then derives workflow states from "
        "canonical feature dependencies. Callers should use the canonical snake_case query "
        "parameters `consumer_system` and `tenant_id`.\n"
        "When: Used directly by lotus-gateway platform capability aggregation and other "
        "downstream discovery clients to enable only supported lotus-core integration paths. "
        "This route is a control-plane discovery contract, not a substitute for endpoint-specific "
        "OpenAPI or source-data product contracts. CamelCase aliases such as `consumerSystem` "
        "and `tenantId` are not supported."
    ),
)
async def get_integration_capabilities(
    request: Request,
    consumer_system: ConsumerSystem = Query(
        "lotus-gateway",
        description="Consumer requesting capability metadata.",
        examples=["lotus-performance"],
    ),
    tenant_id: str = Query(
        ...,
        description="Source-owned tenant identifier required for policy resolution.",
        examples=["tenant_sg_pb"],
    ),
    service: CapabilitiesService = Depends(get_capabilities_service),
) -> IntegrationCapabilitiesResponse:
    tenant_id = bind_admitted_tenant_id(
        requested_tenant_id=tenant_id,
        tenant_context=request.state.tenant_context,
        source_product="IntegrationCapabilities",
    )
    capabilities_service: CapabilitiesService = service
    response = capabilities_service.get_integration_capabilities(
        consumer_system=consumer_system,
        tenant_id=tenant_id,
    )
    return cast(IntegrationCapabilitiesResponse, response)
