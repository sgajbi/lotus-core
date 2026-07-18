from __future__ import annotations

from datetime import date, datetime

from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PortfolioPartyRoleAssignmentRecord(BaseModel):
    portfolio_id: str = Field(
        ..., min_length=1, description="Canonical portfolio receiving the role assignment."
    )
    party_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Source-owned party identifier. It is intentionally not a Lotus party-master FK "
            "until the separately governed party model is available."
        ),
    )
    role_type: PortfolioPartyRoleType = Field(
        ..., description="Governed private-banking capacity in which the party acts."
    )
    role_scope: PortfolioPartyRoleScope = Field(
        ..., description="Responsibility boundary covered by this assignment."
    )
    effective_from: date = Field(..., description="Inclusive assignment start date.")
    effective_to: date | None = Field(
        None, description="Inclusive assignment end date, or null while open-ended."
    )
    assignment_version: int = Field(
        1, ge=1, description="Source-controlled version of this assignment observation."
    )
    source_system: str = Field(
        ..., min_length=1, description="Authoritative system publishing the assignment."
    )
    source_record_id: str = Field(
        ..., min_length=1, description="Stable source record identity used for idempotent replay."
    )
    observed_at: datetime = Field(
        ..., description="Timezone-aware timestamp when the source observed the assignment."
    )
    quality_status: PortfolioPartyRoleQualityStatus = Field(
        PortfolioPartyRoleQualityStatus.ACCEPTED,
        description="Governed data-quality disposition for the source observation.",
    )

    @field_validator("portfolio_id", "party_id", "source_system", "source_record_id")
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier fields must not be blank")
        return value

    @field_validator("observed_at")
    @classmethod
    def require_timezone_aware_observation(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_effective_window(self) -> "PortfolioPartyRoleAssignmentRecord":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self

    model_config = ConfigDict()


class PortfolioPartyRoleAssignmentIngestionRequest(BaseModel):
    party_role_assignments: list[PortfolioPartyRoleAssignmentRecord] = Field(
        ...,
        min_length=1,
        description="Effective-dated portfolio party-role observations to ingest or upsert.",
    )

    @model_validator(mode="after")
    def validate_source_identity_uniqueness(
        self,
    ) -> "PortfolioPartyRoleAssignmentIngestionRequest":
        source_keys = [
            (
                assignment.source_system,
                assignment.source_record_id,
                assignment.assignment_version,
            )
            for assignment in self.party_role_assignments
        ]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("party_role_assignments contains duplicate source identities")
        return self

    model_config = ConfigDict()
