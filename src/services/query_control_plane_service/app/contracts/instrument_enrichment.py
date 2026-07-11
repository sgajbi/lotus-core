"""Public QCP contracts for deterministic bulk instrument enrichment."""

from typing import Literal

from portfolio_common.source_data_product_metadata import product_name_field, product_version_field
from pydantic import BaseModel, ConfigDict, Field


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
