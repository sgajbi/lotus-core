from typing import cast

from fastapi import APIRouter, Depends, Query

from src.services.query_service.app.dtos.capabilities_dto import (
    ConsumerSystem,
    IntegrationCapabilitiesResponse,
)
from src.services.query_service.app.services.capabilities_service import CapabilitiesService

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])


def get_capabilities_service() -> CapabilitiesService:
    return CapabilitiesService()


@router.get(
    "/capabilities",
    response_model=IntegrationCapabilitiesResponse,
    summary="Get lotus-core Integration Capabilities",
    description=(
        "What: Return policy-resolved integration capabilities for a consumer and tenant context.\n"
        "How: Applies environment and tenant-policy overrides, then derives workflow states from "
        "canonical feature dependencies. Callers should use the canonical snake_case query "
        "parameters `consumer_system` and `tenant_id`.\n"
        "When: Used directly by lotus-gateway platform capability aggregation and other "
        "downstream discovery clients to enable only supported lotus-core integration paths. "
        "This route is a control-plane discovery contract, not a substitute for endpoint-specific "
        "OpenAPI or source-data product contracts."
    ),
)
async def get_integration_capabilities(
    consumer_system: ConsumerSystem = Query(
        "lotus-gateway",
        description="Consumer requesting capability metadata.",
        examples=["lotus-performance"],
    ),
    tenant_id: str = Query(
        "default",
        description="Tenant or client identifier for policy resolution.",
        examples=["tenant_sg_pb"],
    ),
    service: CapabilitiesService = Depends(get_capabilities_service),
) -> IntegrationCapabilitiesResponse:
    capabilities_service: CapabilitiesService = service
    response = capabilities_service.get_integration_capabilities(
        consumer_system=consumer_system,
        tenant_id=tenant_id,
    )
    return cast(IntegrationCapabilitiesResponse, response)
