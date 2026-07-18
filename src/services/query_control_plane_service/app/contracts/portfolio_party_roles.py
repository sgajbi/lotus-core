"""API contracts for effective portfolio party-role assignments."""

from datetime import date, datetime
from typing import Literal

from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class PortfolioPartyRoleAssignmentRequest(BaseModel):
    as_of_date: date = Field(
        ..., description="Business date used to resolve effective role assignments."
    )
    party_id: str | None = Field(
        None, description="Optional source-owned party identifier filter."
    )
    role_types: list[PortfolioPartyRoleType] = Field(
        default_factory=list, description="Optional governed role-type filters."
    )
    role_scopes: list[PortfolioPartyRoleScope] = Field(
        default_factory=list, description="Optional responsibility-scope filters."
    )
    include_non_accepted: bool = Field(
        False,
        description="Include latest pending, quarantined, or rejected source observations.",
    )

    model_config = ConfigDict()


class PortfolioPartyRoleAssignmentItem(BaseModel):
    party_id: str = Field(..., description="Source-owned party identifier.")
    role_type: PortfolioPartyRoleType = Field(..., description="Governed banking capacity.")
    role_scope: PortfolioPartyRoleScope = Field(..., description="Responsibility boundary.")
    effective_from: date = Field(..., description="Inclusive assignment start date.")
    effective_to: date | None = Field(None, description="Inclusive assignment end date.")
    assignment_version: int = Field(..., ge=1, description="Selected source version.")
    source_system: str = Field(..., description="Authoritative source system.")
    source_record_id: str = Field(..., description="Stable source record identity.")
    observed_at: datetime = Field(..., description="Source observation timestamp.")
    quality_status: PortfolioPartyRoleQualityStatus = Field(
        ..., description="Quality disposition of the selected source version."
    )

    model_config = ConfigDict()


class PortfolioPartyRoleAssignmentSupportability(BaseModel):
    state: Literal["READY", "INCOMPLETE"]
    reason: Literal["PARTY_ROLE_ASSIGNMENTS_READY", "PARTY_ROLE_ASSIGNMENTS_EMPTY"]
    returned_assignment_count: int = Field(..., ge=0)
    filters_applied: list[str] = Field(default_factory=list)

    model_config = ConfigDict()


class PortfolioPartyRoleAssignmentResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioPartyRoleAssignment"] = product_name_field(
        "PortfolioPartyRoleAssignment"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str
    assignments: list[PortfolioPartyRoleAssignmentItem] = Field(default_factory=list)
    supportability: PortfolioPartyRoleAssignmentSupportability
    lineage: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict()
