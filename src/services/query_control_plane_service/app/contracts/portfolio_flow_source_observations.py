"""Explicit immutable source windows and exact revision lookup, never latest aliases."""

from datetime import date, datetime
from typing import Literal, Self

from portfolio_common.domain.calculation_lineage import require_sha256_digest
from portfolio_common.domain.portfolio_source_observations import require_observation_identity
from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class FlowWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.to_date < self.from_date:
            raise ValueError("ordered inclusive window required")
        return self


class FlowPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_size: StrictInt = Field(ge=1, le=250)
    page_token: str | None = Field(None, min_length=1, max_length=8192)


class PortfolioFlowObservationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_system: str = Field(min_length=1, max_length=128)
    source_cut_id: str = Field(min_length=1, max_length=128)
    cut_revision: StrictInt = Field(ge=1)
    manifest_hash: str
    window: FlowWindow
    currency: str = Field(pattern="^[A-Z]{3}$")
    page: FlowPageRequest

    @model_validator(mode="after")
    def exact_pins(self) -> Self:
        require_observation_identity(self.source_system, "source_system")
        require_observation_identity(self.source_cut_id, "source_cut_id")
        require_sha256_digest(self.manifest_hash, "manifest_hash")
        return self


class FlowTargetPinEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_record_id: str
    observation_id: str
    content_hash: str
    flow_source_record_revision: int


class FlowEventEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_name: str = product_name_field("PortfolioFinancialFlowObservations")
    product_version: str = product_version_field()
    source_record_id: str
    business_date: date
    received_at: datetime
    currency: str
    amount: str = Field(description="Exact canonical decimal text; no float serialization.")
    classification: Literal["EXTERNAL_CASH", "INTERNAL_TRANSFER", "REVERSAL", "IN_KIND"]
    posting_state: Literal["POSTED", "CANCELLED", "UNKNOWN"]
    reversal_state: Literal["NONE", "REVERSES", "UNKNOWN"]
    reverses_source_record_id: str | None
    reversal_target: FlowTargetPinEvidence | None
    economic_event_id: str | None
    transaction_id: str | None
    observation_id: str
    content_hash: str
    source_system: str
    flow_source_record_revision: int
    source_cut_id: str
    definition_version: str
    predecessor_id: str | None
    expected_head_hash: str | None
    receipt_job_id: str
    coverage: Literal["complete", "partial", "missing"]
    qualification: Literal["unqualified"] = "unqualified"


class FlowPage(BaseModel):
    total_count: int
    returned_count: int
    offset: int
    next_page_token: str | None
    ordered_set_hash: str
    dependency_count: int
    dependency_set_hash: str


class FlowEventRevisionResponse(FlowEventEvidence, SourceDataProductRuntimeMetadata):
    product_name: str = product_name_field("PortfolioFinancialFlowObservations")
    product_version: str = product_version_field()


class PortfolioFlowObservationsResponse(SourceDataProductRuntimeMetadata):
    product_name: str = product_name_field("PortfolioFinancialFlowObservations")
    product_version: str = product_version_field()
    portfolio_id: str
    source_system: str
    source_cut_id: str
    cut_revision: int
    manifest_hash: str
    definition_version: str
    currency: str
    window: FlowWindow
    coverage: Literal["complete", "partial", "missing"]
    qualification: Literal["unqualified"] = "unqualified"
    source_fields_available: bool
    authoritative_use_available: Literal[False] = False
    reason_codes: list[str]
    receipt_job_id: str
    received_at: datetime
    predecessor_cut_hash: str | None
    expected_head_hash: str | None
    pagination: FlowPage
    events: list[FlowEventEvidence]
    reversal_dependencies: list[FlowEventEvidence] = Field(
        description="Exact retained closure; amounts are excluded from this window's flow "
        "events and count."
    )
