"""Bounded source classification history contracts shared by ingestion and QCP."""

from datetime import date, timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from portfolio_common.domain.reference_data.classification_history import (
    classification_cut_identity,
)

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class ClassificationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HistoricalClassificationAssignment(ClassificationContract):
    security_id: Identifier
    group_id: Identifier
    effective_from: date = Field(description="Inclusive assignment start.")
    effective_to: date = Field(description="Exclusive assignment end; never inferred.")
    source_record_id: Identifier
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def forward_interval(self) -> Self:
        if self.effective_from >= self.effective_to:
            raise ValueError("Classification assignment requires a forward half-open interval")
        return self


class InstrumentClassificationCut(ClassificationContract):
    producer_id: Identifier
    classification_set_id: Identifier
    source_record_id: Identifier
    source_version: int = Field(strict=True, ge=1)
    predecessor_cut_id: Digest | None = None
    taxonomy_revision: Identifier
    dimension_name: Identifier
    coverage_from: date
    coverage_to: date = Field(description="Exclusive declared source coverage end.")
    observed_at: AwareDatetime
    generated_at: AwareDatetime
    expected_security_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=500)
    expected_group_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=128)
    assignments: tuple[HistoricalClassificationAssignment, ...] = Field(
        min_length=1, max_length=2000
    )

    @model_validator(mode="after")
    def source_shape(self) -> Self:
        if self.coverage_from >= self.coverage_to or self.observed_at > self.generated_at:
            raise ValueError("Classification coverage or source observation order is invalid")
        if (self.source_version == 1) != (self.predecessor_cut_id is None):
            raise ValueError("A correction requires an exact predecessor cut")
        for universe in (self.expected_security_ids, self.expected_group_ids):
            if len(universe) != len(set(universe)):
                raise ValueError("Classification universe contains duplicate identities")
        previous: dict[str, date] = {}
        for row in sorted(
            self.assignments, key=lambda item: (item.security_id, item.effective_from)
        ):
            if (
                row.security_id not in self.expected_security_ids
                or row.group_id not in self.expected_group_ids
                or row.effective_from < self.coverage_from
                or row.effective_to > self.coverage_to
                or row.observed_at > self.observed_at
            ):
                raise ValueError("Classification assignment is outside its declared source scope")
            if row.effective_from < previous.get(row.security_id, row.effective_from):
                raise ValueError("Classification assignment intervals conflict")
            previous[row.security_id] = row.effective_to
        classification_cut_identity(self.model_dump(mode="json"))
        return self

    def identity(self) -> tuple[str, str]:
        return classification_cut_identity(self.model_dump(mode="json"))


class ClassificationHistorySelection(ClassificationContract):
    producer_id: Identifier
    classification_set_id: Identifier
    source_record_id: Identifier
    source_version: int = Field(strict=True, ge=1)
    cut_id: Digest
    content_hash: Digest
    period_start: date
    period_end: date = Field(description="Inclusive requested business-period end.")
    source_as_of: AwareDatetime = Field(description="Independent source observation cutoff.")
    known_at: AwareDatetime = Field(description="Independent Core receipt/knowledge cutoff.")
    expected_security_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=500)
    expected_group_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def selected_period(self) -> Self:
        if self.period_start > self.period_end or self.period_end == date.max:
            raise ValueError("Historical selection requires a bounded forward business period")
        for universe in (self.expected_security_ids, self.expected_group_ids):
            if len(universe) != len(set(universe)):
                raise ValueError("Historical selection universe contains duplicates")
        return self

    @property
    def until(self) -> date:
        return self.period_end + timedelta(days=1)


class RetainedClassificationCut(ClassificationContract):
    cut_id: Digest
    content_hash: Digest
    received_at: AwareDatetime
    source: InstrumentClassificationCut

    @model_validator(mode="after")
    def exact_custody(self) -> Self:
        if (self.cut_id, self.content_hash) != self.source.identity():
            raise ValueError("Retained classification content identity differs")
        if self.source.generated_at > self.received_at:
            raise ValueError("Classification source generation is after Core receipt")
        return self


class ClassificationHistoryEvidence(ClassificationContract):
    status: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
    qualification: Literal["RETAINED_UNQUALIFIED"] = "RETAINED_UNQUALIFIED"
    compatibility: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    selection: ClassificationHistorySelection
    retained_cut: RetainedClassificationCut | None = None
    assignments: tuple[HistoricalClassificationAssignment, ...] = ()
    missing_security_ids: tuple[Identifier, ...] = ()
    reason_codes: tuple[str, ...]


# Complete synthetic request examples prevent generic OpenAPI inference from
# producing invalid equal-date intervals or a version-one predecessor.
CLASSIFICATION_CUT_EXAMPLE = {
    "producer_id": "SYNTHETIC_REFERENCE",
    "classification_set_id": "SYNTHETIC_SECTOR",
    "source_record_id": "SYNTHETIC_JANUARY",
    "source_version": 1,
    "predecessor_cut_id": None,
    "taxonomy_revision": "SYNTHETIC_V1",
    "dimension_name": "sector",
    "coverage_from": "2026-01-01",
    "coverage_to": "2026-02-01",
    "observed_at": "2026-02-01T00:00:00Z",
    "generated_at": "2026-02-01T01:00:00Z",
    "expected_security_ids": ["SYNTHETIC_A", "SYNTHETIC_B"],
    "expected_group_ids": ["TECHNOLOGY", "FINANCE"],
    "assignments": [
        {
            "security_id": security,
            "group_id": group,
            "effective_from": "2026-01-01",
            "effective_to": "2026-02-01",
            "source_record_id": "SYNTHETIC_ROW_" + security,
            "observed_at": "2026-02-01T00:00:00Z",
        }
        for security, group in (("SYNTHETIC_A", "TECHNOLOGY"), ("SYNTHETIC_B", "FINANCE"))
    ],
}
_EXAMPLE_CUT_ID, _EXAMPLE_CONTENT_HASH = InstrumentClassificationCut.model_validate(
    CLASSIFICATION_CUT_EXAMPLE
).identity()
CLASSIFICATION_SELECTION_EXAMPLE = {
    **{
        name: CLASSIFICATION_CUT_EXAMPLE[name]
        for name in (
            "producer_id",
            "classification_set_id",
            "source_record_id",
            "source_version",
            "expected_security_ids",
            "expected_group_ids",
        )
    },
    "cut_id": _EXAMPLE_CUT_ID,
    "content_hash": _EXAMPLE_CONTENT_HASH,
    "period_start": "2026-01-01",
    "period_end": "2026-01-31",
    "source_as_of": "2026-03-01T00:00:00Z",
    "known_at": "2026-12-01T00:00:00Z",
}
