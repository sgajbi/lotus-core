from __future__ import annotations

from datetime import date, datetime

from portfolio_common.domain.valuation.assignments import (
    InstrumentValuationPolicyAssignment,
    ValuationPolicyAssignmentStatus,
    validate_no_overlapping_active_assignments,
)
from portfolio_common.domain.valuation.policy_registry import (
    UnknownValuationPolicyError,
    resolve_position_valuation_policy,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InstrumentValuationPolicyAssignmentRecord(BaseModel):
    """Authoritative effective-dated instrument valuation-policy assignment."""

    tenant_id: str = Field(
        ...,
        min_length=1,
        description="Tenant boundary that owns the valuation-policy assignment.",
        examples=["LOTUS_PB_SG"],
    )
    legal_book_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Legal booking entity or governed accounting book. This field must not be "
            "inferred from booking centre or jurisdiction."
        ),
        examples=["SG_PRIVATE_BANK_BOOK"],
    )
    security_id: str = Field(
        ...,
        min_length=1,
        description="Canonical instrument identifier governed by the instrument master.",
        examples=["BOND_US_CORP_2031"],
    )
    policy_id: str = Field(
        ...,
        min_length=1,
        description="Exact supported valuation-policy identifier; no product default is applied.",
        examples=["CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL"],
    )
    policy_version: int = Field(
        ...,
        ge=1,
        description="Exact supported policy version; version fallback is prohibited.",
        examples=[1],
    )
    valid_from: date = Field(..., description="Inclusive policy-assignment start date.")
    valid_to: date | None = Field(
        None,
        description="Inclusive policy-assignment end date, or null while open-ended.",
    )
    assignment_status: ValuationPolicyAssignmentStatus = Field(
        ...,
        description="Governed lifecycle state for this source assertion.",
    )
    assignment_version: int = Field(
        ...,
        ge=1,
        description="Monotonically increasing correction version for the source record.",
        examples=[1],
    )
    source_system: str = Field(
        ...,
        min_length=1,
        description="Authoritative source system publishing the policy assignment.",
        examples=["security_master"],
    )
    source_record_id: str = Field(
        ...,
        min_length=1,
        description="Stable source record identity used for idempotent correction history.",
        examples=["VALPOL-BOND_US_CORP_2031-SG"],
    )
    source_revision: str = Field(
        ...,
        min_length=1,
        description="Source-native revision or change token retained for calculation lineage.",
        examples=["rev-2026-07-19-001"],
    )
    observed_at: datetime = Field(
        ...,
        description="Timezone-aware instant when the authoritative source observed the record.",
        examples=["2026-07-19T09:30:00+08:00"],
    )
    assignment_reason: str = Field(
        ...,
        min_length=1,
        description=(
            "Auditable business rationale for the policy selection or correction, such as "
            "clean-price fixed-income treatment."
        ),
        examples=["Fixed-rate bond quoted clean as percentage of face amount."],
    )

    @field_validator(
        "tenant_id",
        "legal_book_id",
        "security_id",
        "policy_id",
        "source_system",
        "source_record_id",
        "source_revision",
        "assignment_reason",
    )
    @classmethod
    def normalize_nonblank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifier and rationale fields must not be blank")
        return normalized

    @field_validator("observed_at")
    @classmethod
    def require_timezone_aware_observation(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_assignment_semantics(self) -> "InstrumentValuationPolicyAssignmentRecord":
        assignment = self.to_domain()
        try:
            resolve_position_valuation_policy(assignment.policy_id, assignment.policy_version)
        except UnknownValuationPolicyError as error:
            raise ValueError(str(error)) from error
        return self

    def to_domain(self) -> InstrumentValuationPolicyAssignment:
        return InstrumentValuationPolicyAssignment(
            tenant_id=self.tenant_id,
            legal_book_id=self.legal_book_id,
            security_id=self.security_id,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            assignment_status=self.assignment_status,
            assignment_version=self.assignment_version,
            source_system=self.source_system,
            source_record_id=self.source_record_id,
            source_revision=self.source_revision,
            observed_at=self.observed_at,
            assignment_reason=self.assignment_reason,
        )

    model_config = ConfigDict()


class InstrumentValuationPolicyAssignmentIngestionRequest(BaseModel):
    valuation_policy_assignments: list[InstrumentValuationPolicyAssignmentRecord] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description=(
            "Source-versioned, effective-dated instrument valuation-policy assignments to "
            "validate and persist atomically."
        ),
    )

    @model_validator(mode="after")
    def validate_batch_authority(self) -> "InstrumentValuationPolicyAssignmentIngestionRequest":
        assignments = [record.to_domain() for record in self.valuation_policy_assignments]
        source_versions = [
            (*assignment.source_record_key, assignment.assignment_version)
            for assignment in assignments
        ]
        if len(source_versions) != len(set(source_versions)):
            raise ValueError(
                "valuation_policy_assignments contains duplicate source-version identities"
            )
        validate_no_overlapping_active_assignments(assignments)
        return self

    model_config = ConfigDict()
