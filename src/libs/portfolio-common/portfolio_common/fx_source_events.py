"""One bounded typed canonical cut, not a sequence of independent FX writes."""

import json
from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from .domain.market_data.fx_source import (
    MAX_FX_CUT_MEMBERS,
    FxSourceCut,
    FxSourceRevision,
    FxSourceScope,
)
from .events import CoreEventModel
from .pydantic_financial_numeric import ExactDecimal18_10

MAX_FX_CUT_ENCODED_PAYLOAD_BYTES = 524288


class FxSourceMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_record_id: str = Field(min_length=1, max_length=128)
    source_revision: str = Field(min_length=1, max_length=128)
    from_currency: str = Field(pattern="^[A-Z]{3}$")
    to_currency: str = Field(pattern="^[A-Z]{3}$")
    rate_date: date
    rate: ExactDecimal18_10
    source_observed_at: AwareDatetime
    fixing_kind: str = Field(min_length=1, max_length=128)
    calendar_version: str = Field(min_length=1, max_length=128)
    predecessor_revision_id: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")

    def to_revision(self, scope: FxSourceScope) -> FxSourceRevision:
        return FxSourceRevision(scope=scope, **self.model_dump(mode="python"))


class FxSourceCutSubmission(BaseModel):
    """Source references only; scope identity is derived from verified server tenant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["fx.source-cut.v1"]
    provider_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    source_cut_reference: str = Field(min_length=1, max_length=128)
    source_cut_revision: str = Field(min_length=1, max_length=128)
    source_observed_cutoff: AwareDatetime
    declared_member_count: StrictInt = Field(ge=1, le=MAX_FX_CUT_MEMBERS)
    declared_membership_hash: str = Field(pattern="^[0-9a-f]{64}$")
    members: tuple[FxSourceMember, ...] = Field(min_length=1, max_length=MAX_FX_CUT_MEMBERS)

    def to_cut(self, tenant_id: str) -> FxSourceCut:
        scope = FxSourceScope(tenant_id, self.provider_id, self.source_id)
        return FxSourceCut(
            scope=scope,
            source_cut_reference=self.source_cut_reference,
            source_cut_revision=self.source_cut_revision,
            source_observed_cutoff=self.source_observed_cutoff,
            revisions=tuple(member.to_revision(scope) for member in self.members),
            declared_member_count=self.declared_member_count,
            declared_membership_hash=self.declared_membership_hash,
        )


class FxCutAuthorizationClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    purpose: Literal["lotus-core.fx-source-cut-admission"] = "lotus-core.fx-source-cut-admission"
    audience: Literal["lotus-core.persistence-service"] = "lotus-core.persistence-service"
    issuer: str = Field(min_length=1, max_length=128)
    key_id: str = Field(min_length=1, max_length=128)
    principal: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    provider_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    enrollment_version: str = Field(min_length=1, max_length=128)
    calendar_version: str = Field(min_length=1, max_length=128)
    cut_id: str = Field(pattern="^[0-9a-f]{64}$")
    content_hash: str = Field(pattern="^[0-9a-f]{64}$")
    accepted_at: AwareDatetime
    expires_at: AwareDatetime


class SignedFxCutAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claims: FxCutAuthorizationClaims
    signature: str = Field(pattern="^[0-9a-f]{64}$")


class FxSourceCutReceivedEvent(CoreEventModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["FxSourceCutReceived"] = "FxSourceCutReceived"
    schema_version: Literal["1.0.0"] = "1.0.0"
    tenant_id: str = Field(min_length=1, max_length=128)
    cut: FxSourceCutSubmission
    authorization: SignedFxCutAuthorization

    def source_cut(self) -> FxSourceCut:
        return self.cut.to_cut(self.tenant_id)

    def bounded_payload(self) -> dict[str, Any]:
        """Bound the actual value encoding used by KafkaProducer, before job/publish."""
        payload: dict[str, Any] = self.model_dump(mode="json")
        if len(json.dumps(payload, default=str).encode("utf-8")) > MAX_FX_CUT_ENCODED_PAYLOAD_BYTES:
            raise ValueError("FX_SOURCE_CUT_ENCODED_SIZE_EXCEEDED")
        return payload


class FxRetainedCutMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    revision_id: str = Field(pattern="^[0-9a-f]{64}$")
    content_hash: str = Field(pattern="^[0-9a-f]{64}$")


class FxSourceCutPersistedEvent(CoreEventModel):
    """Notification of retained authority, never an unscoped valuation correction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: Literal["FxSourceCutPersisted"] = "FxSourceCutPersisted"
    schema_version: Literal["1.0.0"] = "1.0.0"
    contract_version: Literal["fx.source-cut.v1"] = "fx.source-cut.v1"
    tenant_id: str = Field(min_length=1, max_length=128)
    provider_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    cut_id: str = Field(pattern="^[0-9a-f]{64}$")
    content_hash: str = Field(pattern="^[0-9a-f]{64}$")
    member_count: StrictInt = Field(ge=1, le=MAX_FX_CUT_MEMBERS)
    members: tuple[FxRetainedCutMember, ...] = Field(min_length=1, max_length=MAX_FX_CUT_MEMBERS)
    accepted_at: AwareDatetime
    source_observed_cutoff: AwareDatetime

    @model_validator(mode="after")
    def validate_retained_members(self) -> "FxSourceCutPersistedEvent":
        if (
            len(self.members) != self.member_count
            or len({member.revision_id for member in self.members}) != self.member_count
        ):
            raise ValueError("FX_SOURCE_CUT_MEMBERS_INVALID")
        if self.source_observed_cutoff > self.accepted_at:
            raise ValueError("FX_SOURCE_CUT_TIME_INVALID")
        return self
