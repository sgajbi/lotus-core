"""Strict producer facts; tenant identity and qualification are never request fields."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from portfolio_common.api_contract.portfolio_source_verification import (
    SignedObservationVerificationReceipt,
)
from portfolio_common.domain.portfolio_flow_source_observations import (
    FlowEventObservation,
    FlowEventPin,
    FlowSourceCut,
)
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationConflict,
    ObservationCoverage,
    ObservationEnvelope,
    require_observation_hash,
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


class FlowEventPinRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_record_id: str = Field(
        description="Stable producer event identity for this exact revision.", examples=["a"]
    )
    observation_id: str = Field(
        description="Actual retained observation identity.",
        examples=["b8a00e49ac3da06114a5ee56c5538943dbe7c38d6d8122d3ef0b930aeb20b06b"],
    )
    content_hash: str = Field(
        description="Exact retained flow fact hash.",
        examples=["b8a00e49ac3da06114a5ee56c5538943dbe7c38d6d8122d3ef0b930aeb20b06b"],
    )
    flow_source_record_revision: StrictInt = Field(
        ge=1, description="Exact retained source revision.", examples=[1]
    )


class FlowEventObservationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(description="Portfolio within the authenticated tenant.")
    source_system: str = Field(description="Producer identity; must match authenticated service.")
    source_record_id: str = Field(
        description="Stable financial source event identity within tenant, portfolio and producer."
    )
    flow_source_record_revision: StrictInt = Field(
        ge=1, description="Contiguous financial source event revision, not a product version."
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
            source_revision=self.flow_source_record_revision,
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

    business_date: date
    currency: str
    amount: Decimal
    classification: Literal["EXTERNAL_CASH", "INTERNAL_TRANSFER", "REVERSAL", "IN_KIND"]
    posting_state: Literal["POSTED", "CANCELLED", "UNKNOWN"]
    reversal_state: Literal["NONE", "REVERSES", "UNKNOWN"]
    reverses_source_record_id: str | None
    reversal_target: FlowEventPinRecord | None = Field(
        description="Exact retained target revision; explicit null without reversal."
    )
    economic_event_id: str | None = None
    transaction_id: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def require_exact_amount(cls, value):
        if not isinstance(value, (str, Decimal)):
            raise ValueError("flow amount requires exact decimal text")
        return value

    def _fact(self, tenant_id: str) -> FlowEventObservation:
        return FlowEventObservation(
            self.envelope(tenant_id),
            business_date=self.business_date,
            currency=self.currency,
            amount=self.amount,
            classification=self.classification,
            posting_state=self.posting_state,
            reversal_state=self.reversal_state,
            reverses_source_record_id=self.reverses_source_record_id,
            reversal_target=FlowEventPin(**self.reversal_target.model_dump())
            if self.reversal_target is not None
            else None,
            economic_event_id=self.economic_event_id,
            transaction_id=self.transaction_id,
        )

    @model_validator(mode="after")
    def validate_flow(self) -> Self:
        if self.verification_receipt is not None:
            raise ValueError("flow fact verification receipts are not supported")
        self._fact("request-shape-validation")
        return self

    def to_observation(self, tenant_id: str) -> FlowEventObservation:
        fact = self._fact(tenant_id)
        require_observation_hash(fact, self.content_hash)
        return fact


class FlowEventObservationIngestionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "observations": [
                        {
                            "portfolio_id": "portfolio-synthetic",
                            "source_record_id": "a",
                            "source_cut_id": "source-cut",
                            "definition_version": "v1",
                            "effective_from": "2026-01-01",
                            "effective_to": "2026-02-01",
                            "observed_at": "2026-01-31 00:00:00+00:00",
                            "generated_at": "2026-01-31 00:00:00+00:00",
                            "coverage": "complete",
                            "coverage_scope": "monthly-explicit-events",
                            "predecessor_id": None,
                            "expected_head_hash": None,
                            "source_system": "producer-synthetic",
                            "flow_source_record_revision": 1,
                            "business_date": "2026-01-02",
                            "currency": "SGD",
                            "amount": "10.001000000000000000001",
                            "classification": "EXTERNAL_CASH",
                            "posting_state": "POSTED",
                            "reversal_state": "NONE",
                            "reverses_source_record_id": None,
                            "reversal_target": None,
                            "economic_event_id": None,
                            "transaction_id": None,
                            "content_hash": (
                                "b8a00e49ac3da06114a5ee56c5538943dbe7c38d6d8122d3ef0b930aeb20b06b"
                            ),
                        }
                    ]
                }
            ]
        },
    )
    observations: list[FlowEventObservationRecord] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_distinct_records(self) -> Self:
        identities = [
            (r.portfolio_id, r.source_system, r.source_record_id) for r in self.observations
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("batch requires one revision per producer source event identity")
        return self


class FlowSourceCutRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    portfolio_id: str
    source_system: str
    source_cut_id: str
    cut_revision: StrictInt = Field(ge=1)
    definition_version: str = Field(
        description="Exact producer flow definition version.", examples=["v1"]
    )
    currency: str
    coverage_from: date
    coverage_to: date
    coverage: ObservationCoverage
    event_pins: list[FlowEventPinRecord] = Field(max_length=1000)
    dependency_pins: list[FlowEventPinRecord] = Field(
        max_length=1000,
        description="Ordered exact retained reversal dependency closure, separate from window "
        "membership.",
    )
    predecessor_cut_hash: str | None = Field(
        description="Previous immutable cut hash, explicitly null for revision one.",
        examples=["148103c8d030fdfa28f19c8b1ea584f1f0610edad582d85d02fe47246da33e36", None],
    )
    expected_head_hash: str | None = Field(
        description="Exact current cut head for CAS, explicitly null for revision one.",
        examples=[None],
    )
    producer_manifest_hash: str = Field(
        description="Canonical tenant-bound complete manifest hash.",
        examples=["148103c8d030fdfa28f19c8b1ea584f1f0610edad582d85d02fe47246da33e36"],
    )

    def _cut(self, tenant_id: str) -> FlowSourceCut:
        return FlowSourceCut(
            tenant_id=tenant_id,
            **self.model_dump(exclude={"event_pins", "dependency_pins", "producer_manifest_hash"}),
            event_pins=tuple(FlowEventPin(**p.model_dump()) for p in self.event_pins),
            dependency_pins=tuple(FlowEventPin(**p.model_dump()) for p in self.dependency_pins),
        )

    @model_validator(mode="after")
    def validate_cut(self) -> Self:
        self._cut("request-shape-validation")
        from portfolio_common.domain.calculation_lineage import require_sha256_digest

        require_sha256_digest(self.producer_manifest_hash, "producer_manifest_hash")
        return self

    def to_cut(self, tenant_id: str) -> FlowSourceCut:
        cut = self._cut(tenant_id)
        if cut.content_hash != self.producer_manifest_hash:
            raise ObservationConflict("FLOW_SOURCE_CUT_HASH_MISMATCH")
        return cut


class FlowSourceCutIngestionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "cuts": [
                        {
                            "portfolio_id": "portfolio-synthetic",
                            "source_system": "producer-synthetic",
                            "source_cut_id": "source-cut",
                            "cut_revision": 1,
                            "definition_version": "v1",
                            "currency": "SGD",
                            "coverage_from": "2026-01-01",
                            "coverage_to": "2026-01-31",
                            "coverage": "complete",
                            "event_pins": [
                                {
                                    "source_record_id": "a",
                                    "observation_id": (
                                        "b8a00e49ac3da06114a5ee56c5538943dbe7c38d6d8122d3ef0b930aeb20b06b"
                                    ),
                                    "content_hash": (
                                        "b8a00e49ac3da06114a5ee56c5538943dbe7c38d6d8122d3ef0b930aeb20b06b"
                                    ),
                                    "flow_source_record_revision": 1,
                                }
                            ],
                            "dependency_pins": [],
                            "predecessor_cut_hash": None,
                            "expected_head_hash": None,
                            "producer_manifest_hash": (
                                "148103c8d030fdfa28f19c8b1ea584f1f0610edad582d85d02fe47246da33e36"
                            ),
                        }
                    ]
                }
            ]
        },
    )
    cuts: list[FlowSourceCutRecord] = Field(min_length=1, max_length=1)
