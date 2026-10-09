"""Strict producer facts; tenant identity and qualification are never request fields."""

from datetime import date, datetime
from decimal import Decimal
from typing import Self

from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationCoverage,
    ObservationEnvelope,
    require_observation_hash,
)
from portfolio_common.domain.portfolio_source_verification import (
    SignedObservationVerificationReceipt,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)


class SourceObservationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(description="Portfolio within the authenticated tenant.")
    source_system: str = Field(description="Producer identity; must match authenticated service.")
    source_record_id: str = Field(description="Stable producer record identity.")
    source_version: StrictInt = Field(
        ge=1, description="Contiguous producer revision, starting at 1."
    )
    source_cut_id: str = Field(
        description="Producer cut identity, not a cross-product compatibility claim."
    )
    definition_version: str = Field(description="Producer fact definition version.")
    effective_from: date = Field(description="Inclusive business-date start.")
    effective_to: date | None = Field(description="Exclusive business-date end, null when ongoing.")
    observed_at: datetime = Field(description="Timezone-aware source observation timestamp.")
    generated_at: datetime = Field(description="Timezone-aware source generation timestamp.")
    coverage: ObservationCoverage = Field(
        description="Complete, partial or missing source coverage."
    )
    coverage_scope: str = Field(description="Producer-declared coverage boundary, not approval.")
    predecessor_id: str | None = Field(
        None, description="Original immutable observation ID for correction."
    )
    expected_head_hash: str | None = Field(
        None, description="Compare-and-swap hash of the current head."
    )
    content_hash: str = Field(
        description="Verified canonical typed fact hash, 64 lower-case hex characters."
    )
    verification_receipt: SignedObservationVerificationReceipt | None = Field(
        None,
        exclude_if=lambda value: value is None,
        description="Independent fact-verification attestation, not producer or monthly approval.",
    )

    def envelope(self, tenant_id: str) -> ObservationEnvelope:
        """Map public lineage vocabulary explicitly; no alternative aliases are accepted."""
        return ObservationEnvelope(
            tenant_id=tenant_id,
            portfolio_id=self.portfolio_id,
            producer_id=self.source_system,
            source_record_id=self.source_record_id,
            source_revision=self.source_version,
            source_cut_id=self.source_cut_id,
            definition_version=self.definition_version,
            effective_from=self.effective_from,
            effective_to=self.effective_to,
            observed_at=self.observed_at,
            generated_at=self.generated_at,
            coverage=self.coverage,
            coverage_scope=self.coverage_scope,
            predecessor_id=self.predecessor_id,
            expected_head_hash=self.expected_head_hash,
        )

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        self.envelope("request-shape-validation")
        return self


class CashAvailabilityObservationRecord(SourceObservationRecord):
    currency: str = Field(description="Declared ISO-style uppercase three-letter currency.")
    settled_amount: Decimal | None = Field(
        description="Independent settled amount; null is unobserved."
    )
    encumbered_amount: Decimal | None = Field(
        description="Independent encumbered amount; no formula inferred."
    )
    available_amount: Decimal | None = Field(
        description="Independent available amount; zero is observed."
    )

    @field_validator("settled_amount", "encumbered_amount", "available_amount", mode="before")
    @classmethod
    def reject_inexact_numbers(cls, value):
        if value is not None and not isinstance(value, (Decimal, str)):
            raise ValueError("source amounts require exact decimal strings or Decimal values")
        return value

    @model_validator(mode="after")
    def validate_cash(self) -> Self:
        self._fact("request-shape-validation")
        return self

    def _fact(self, tenant_id: str) -> CashAvailabilityObservation:
        return CashAvailabilityObservation(
            self.envelope(tenant_id),
            self.currency,
            self.settled_amount,
            self.encumbered_amount,
            self.available_amount,
        )

    def to_observation(self, tenant_id: str) -> CashAvailabilityObservation:
        fact = self._fact(tenant_id)
        require_observation_hash(fact, self.content_hash)
        return fact


class FundingInvestmentObservationRecord(SourceObservationRecord):
    funded: StrictBool | None = Field(
        description="Independent producer-funded assertion, not ledger-derived."
    )
    invested: StrictBool | None = Field(
        description="Independent producer-invested assertion, not lifecycle-derived."
    )

    def to_observation(self, tenant_id: str) -> FundingInvestmentObservation:
        fact = FundingInvestmentObservation(self.envelope(tenant_id), self.funded, self.invested)
        require_observation_hash(fact, self.content_hash)
        return fact


def _require_distinct_records(records: list[SourceObservationRecord]) -> None:
    identities = [(r.portfolio_id, r.source_system, r.source_record_id) for r in records]
    if len(set(identities)) != len(identities):
        raise ValueError("batch requires one revision per producer record identity")


class CashAvailabilityObservationIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[CashAvailabilityObservationRecord] = Field(
        min_length=1, max_length=100, description="Atomic batch of immutable cash source facts."
    )

    @model_validator(mode="after")
    def require_distinct_records(self) -> Self:
        _require_distinct_records(list(self.observations))
        return self


class FundingInvestmentObservationIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[FundingInvestmentObservationRecord] = Field(
        min_length=1,
        max_length=100,
        description="Atomic batch of independent funding/investment facts.",
    )

    @model_validator(mode="after")
    def require_distinct_records(self) -> Self:
        _require_distinct_records(list(self.observations))
        return self
