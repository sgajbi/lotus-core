from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .source_data_product_identity import product_name_field, product_version_field


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


class InstrumentEnrichmentBulkRequest(BaseModel):
    security_ids: list[str] = Field(
        ...,
        description=(
            "Canonical Lotus security identifiers to enrich in one deterministic batch. "
            "Order is preserved in the response."
        ),
        examples=[["SEC_AAPL_US", "SEC_MSFT_US"]],
        min_length=1,
    )

    model_config = ConfigDict()


class InstrumentEnrichmentRecord(BaseModel):
    security_id: str = Field(
        ...,
        description="Canonical Lotus security identifier.",
        examples=["SEC_AAPL_US"],
    )
    issuer_id: str | None = Field(
        None,
        description="Canonical direct issuer identifier, null when the security is unknown.",
        examples=["ISSUER_APPLE_INC"],
    )
    issuer_name: str | None = Field(
        None,
        description="Display name for direct issuer, null when the security is unknown.",
        examples=["Apple Inc."],
    )
    ultimate_parent_issuer_id: str | None = Field(
        None,
        description="Canonical ultimate parent issuer identifier, when available.",
        examples=["ISSUER_APPLE_HOLDING"],
    )
    ultimate_parent_issuer_name: str | None = Field(
        None,
        description="Display name for ultimate parent issuer, when available.",
        examples=["Apple Holdings PLC"],
    )
    liquidity_tier: str | None = Field(
        None,
        description=(
            "Liquidity tier used by suitability and concentration workflows, when available."
        ),
        examples=["L1", "L5"],
    )

    model_config = ConfigDict()


class InstrumentEnrichmentBulkResponse(BaseModel):
    product_name: Literal["InstrumentReferenceBundle"] = product_name_field(
        "InstrumentReferenceBundle"
    )
    product_version: Literal["v1"] = product_version_field()
    records: list[InstrumentEnrichmentRecord] = Field(
        ...,
        description=(
            "Deterministic enrichment records in the same order as request security_ids. "
            "Unknown securities remain present with null enrichment fields."
        ),
        examples=[
            [
                {
                    "security_id": "SEC_AAPL_US",
                    "issuer_id": "ISSUER_APPLE_INC",
                    "issuer_name": "Apple Inc.",
                    "ultimate_parent_issuer_id": "ISSUER_APPLE_HOLDING",
                    "ultimate_parent_issuer_name": "Apple Holdings PLC",
                    "liquidity_tier": "L1",
                }
            ]
        ],
    )

    model_config = ConfigDict()
