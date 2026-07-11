"""Public QCP contracts for effective integration policy diagnostics."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyProvenanceMetadata(BaseModel):
    policy_version: str = Field(
        ...,
        description="Version label for the resolved integration policy.",
        examples=["tenant-default-v1"],
    )
    policy_source: str = Field(
        ...,
        description="Policy source level used for resolution.",
        examples=["tenant"],
    )
    matched_rule_id: str = Field(
        ...,
        description="Deterministic identifier of the matched policy rule.",
        examples=["tenant.tenant_sg_pb.consumers.lotus-performance"],
    )
    strict_mode: bool = Field(
        ...,
        description="Whether strict section gating is enforced for this policy context.",
        examples=[True],
    )

    model_config = ConfigDict()


class EffectiveIntegrationPolicyResponse(BaseModel):
    contract_version: str = Field(
        "v1",
        description="Version of the integration policy response contract.",
        examples=["v1"],
    )
    source_service: str = Field(
        "lotus-core",
        description="Service producing the policy response.",
        examples=["lotus-core"],
    )
    consumer_system: str = Field(
        ...,
        description="Canonical downstream consumer system identifier.",
        examples=["lotus-performance"],
    )
    tenant_id: str = Field(
        ...,
        description="Tenant identifier used for policy resolution.",
        examples=["tenant_sg_pb"],
    )
    generated_at: datetime = Field(
        ...,
        description="UTC timestamp when the policy response was generated.",
        examples=["2026-03-01T12:00:00Z"],
    )
    policy_provenance: PolicyProvenanceMetadata = Field(
        ...,
        description="Policy lineage metadata showing how the effective policy was resolved.",
        examples=[
            {
                "policy_version": "tenant-default-v1",
                "policy_source": "tenant",
                "matched_rule_id": "tenant.tenant_sg_pb.consumers.lotus-performance",
                "strict_mode": True,
            }
        ],
    )
    allowed_sections: list[str] = Field(
        default_factory=list,
        description="Section allow-list resolved for this consumer and tenant.",
        examples=[["OVERVIEW", "HOLDINGS"]],
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal policy diagnostics relevant to consumer behavior.",
        examples=[["NO_ALLOWED_SECTION_RESTRICTION"]],
    )

    model_config = ConfigDict()
