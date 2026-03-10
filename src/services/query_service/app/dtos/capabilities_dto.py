from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ConsumerSystem = Literal["lotus-gateway", "lotus-performance", "lotus-manage", "UI", "UNKNOWN"]


class FeatureCapability(BaseModel):
    key: str = Field(
        ...,
        description="Canonical feature key.",
        examples=["lotus_core.ingestion.bulk_upload_adapter"],
    )
    enabled: bool = Field(
        ...,
        description="Whether this feature is enabled.",
        examples=[True],
    )
    owner_service: str = Field(
        ...,
        description="Owning service for the feature capability.",
        examples=["lotus-core"],
    )
    description: str = Field(
        ...,
        description="Human-readable capability summary.",
        examples=["CSV/XLSX preview and commit support for onboarding workflows."],
    )


class WorkflowCapability(BaseModel):
    workflow_key: str = Field(
        ...,
        description="Workflow identifier.",
        examples=["portfolio_bulk_onboarding"],
    )
    enabled: bool = Field(
        ...,
        description="Whether workflow is enabled for current context.",
        examples=[True],
    )
    required_features: list[str] = Field(
        default_factory=list,
        description="Feature keys required for workflow execution.",
        examples=[
            [
                "lotus_core.ingestion.bulk_upload_adapter",
                "lotus_core.ingestion.portfolio_bundle_adapter",
            ]
        ],
    )


class IntegrationCapabilitiesResponse(BaseModel):
    contract_version: str = Field(
        ...,
        description="Version of the capabilities response contract.",
        examples=["v1"],
    )
    source_service: str = Field(
        ...,
        description="Service emitting capability metadata.",
        examples=["lotus-core"],
    )
    consumer_system: ConsumerSystem = Field(
        ...,
        description="Canonical consumer system receiving capabilities.",
        examples=["lotus-performance"],
    )
    tenant_id: str = Field(
        ...,
        description="Tenant identifier used for capability policy resolution.",
        examples=["tenant_sg_pb"],
    )
    generated_at: datetime = Field(
        ...,
        description="UTC timestamp when capability payload was generated.",
        examples=["2026-03-01T12:00:00Z"],
    )
    as_of_date: date = Field(
        ...,
        description="Business date at which capability policy is effective.",
        examples=["2026-03-01"],
    )
    policy_version: str = Field(
        ...,
        description="Resolved policy version for tenant capability controls.",
        examples=["tenant-default-v1"],
    )
    supported_input_modes: list[str] = Field(
        ...,
        description="Supported integration input modes for the consumer context.",
        examples=[["lotus_core_ref", "inline_bundle", "file_upload"]],
    )
    features: list[FeatureCapability] = Field(
        ...,
        description="Feature-level capability flags and ownership metadata.",
    )
    workflows: list[WorkflowCapability] = Field(
        ...,
        description="Workflow-level capability flags derived from feature dependencies.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "contract_version": "v1",
                "source_service": "lotus-core",
                "consumer_system": "lotus-gateway",
                "tenant_id": "default",
                "generated_at": "2026-02-23T21:00:00Z",
                "as_of_date": "2026-02-23",
                "policy_version": "tenant-default-v1",
                "supported_input_modes": ["lotus_core_ref", "inline_bundle"],
                "features": [
                    {
                        "key": "lotus_core.ingestion.bulk_upload_adapter",
                        "enabled": True,
                        "owner_service": "lotus-core",
                        "description": (
                            "CSV/XLSX preview+commit adapter endpoints for onboarding workflows."
                        ),
                    }
                ],
                "workflows": [
                    {
                        "workflow_key": "portfolio_bulk_onboarding",
                        "enabled": True,
                        "required_features": [
                            "lotus_core.ingestion.bulk_upload_adapter",
                            "lotus_core.ingestion.portfolio_bundle_adapter",
                        ],
                    }
                ],
            }
        },
    }
