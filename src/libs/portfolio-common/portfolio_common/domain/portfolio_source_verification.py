"""Fact-receipt identity, separate from monthly assembly or financial approval."""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .calculation_lineage import require_sha256_digest
from .portfolio_source_observations import (
    CashAvailabilityObservation,
    ObservationEnvelope,
    ObservationFamily,
    PortfolioSourceObservation,
    require_observation_identity,
)


class ObservationVerificationSubject(BaseModel):
    """Expected identity resolved from custody, never inferred from a signed assertion.

    The owning adapter must resolve the complete cut manifest independently. A page
    hash, matching date, or issuer-supplied manifest hash cannot supply that authority.
    This model neither mutates the observation nor qualifies a monthly assembly.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    family: ObservationFamily
    envelope: ObservationEnvelope
    content_hash: str
    source_cut_manifest_hash: str
    consumer_id: str
    currency: str | None
    as_of_date: date

    @field_validator("envelope", mode="before")
    @classmethod
    def require_exact_revision(
        cls, value: ObservationEnvelope | dict[str, object]
    ) -> ObservationEnvelope | dict[str, object]:
        # Wire parsing must not turn True or "1" into the original integer revision.
        revision = (
            value.get("source_revision") if isinstance(value, dict) else value.source_revision
        )
        if type(revision) is not int:
            raise ValueError("verification requires exact integer source revision")
        return value

    @field_validator("content_hash", "source_cut_manifest_hash")
    @classmethod
    def require_digest(cls, value: str) -> str:
        require_sha256_digest(value, "verification_digest")
        return value

    @field_validator("consumer_id")
    @classmethod
    def require_consumer(cls, value: str) -> str:
        require_observation_identity(value, "consumer_id")
        return value

    @model_validator(mode="after")
    def require_family_currency_and_effective_date(self) -> Self:
        if self.family == ObservationFamily.CASH_AVAILABILITY:
            if (
                self.currency is None
                or len(self.currency) != 3
                or not self.currency.isascii()
                or not self.currency.isalpha()
                or not self.currency.isupper()
            ):
                raise ValueError("cash verification requires exact currency")
        elif self.currency is not None:
            raise ValueError("readiness verification cannot invent a currency")
        if not self.envelope.is_effective(self.as_of_date):
            raise ValueError("verification business date outside fact interval")
        return self

    @classmethod
    def from_observation(
        cls,
        observation: PortfolioSourceObservation,
        *,
        source_cut_manifest_hash: str,
        consumer_id: str,
        as_of_date: date,
    ) -> Self:
        return cls(
            family=observation.family,
            envelope=observation.envelope,
            content_hash=observation.content_hash,
            source_cut_manifest_hash=source_cut_manifest_hash,
            consumer_id=consumer_id,
            currency=observation.currency
            if isinstance(observation, CashAvailabilityObservation)
            else None,
            as_of_date=as_of_date,
        )


class ObservationVerificationClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    product_name: Literal["PortfolioSourceFactVerificationReceipt"] = (
        "PortfolioSourceFactVerificationReceipt"
    )
    product_version: Literal["v1"] = "v1"
    purpose: Literal["PORTFOLIO_FINANCIAL_SOURCE_FACT"] = "PORTFOLIO_FINANCIAL_SOURCE_FACT"
    issuer_id: str
    key_id: str
    artifact_revision: str
    subject: ObservationVerificationSubject
    issued_at: datetime
    expires_at: datetime

    @field_validator("issuer_id", "key_id", "artifact_revision")
    @classmethod
    def require_identity(cls, value: str) -> str:
        require_observation_identity(value, "verification_identity")
        return value

    @model_validator(mode="after")
    def require_validity(self) -> Self:
        if any(value.utcoffset() is None for value in (self.issued_at, self.expires_at)):
            raise ValueError("verification validity requires timezone-aware instants")
        if self.expires_at <= self.issued_at:
            raise ValueError("verification validity must be nonempty")
        if self.subject.envelope.generated_at > self.issued_at:
            raise ValueError("verification cannot precede source generation")
        return self


class ObservationVerificationScope(BaseModel):
    """Reusable server registration, not a caller assertion or monthly authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: str
    portfolio_id: str
    producer_id: str
    family: ObservationFamily
    consumer_id: str
    currency: str | None
    definition_version: str
    coverage_scope: str

    @field_validator(
        "tenant_id",
        "portfolio_id",
        "producer_id",
        "consumer_id",
        "definition_version",
        "coverage_scope",
    )
    @classmethod
    def require_scope_identity(cls, value: str) -> str:
        require_observation_identity(value, "verification_scope")
        return value

    @classmethod
    def from_subject(cls, subject: ObservationVerificationSubject) -> Self:
        return cls(
            tenant_id=subject.envelope.tenant_id,
            portfolio_id=subject.envelope.portfolio_id,
            producer_id=subject.envelope.producer_id,
            family=subject.family,
            consumer_id=subject.consumer_id,
            currency=subject.currency,
            definition_version=subject.envelope.definition_version,
            coverage_scope=subject.envelope.coverage_scope,
        )


class SignedObservationVerificationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    claims: ObservationVerificationClaims
    signature: str

    @field_validator("signature")
    @classmethod
    def require_signature(cls, value: str) -> str:
        require_sha256_digest(value, "signature")
        return value
