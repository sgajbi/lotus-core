"""Closed neutral producer inputs; callers select native sources, never submit proof bodies."""

from datetime import date, datetime
from typing import Self, cast

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import (
    DeclaredCoverage,
    FinancialSourceCutManifest,
    HistoricalRegistryCut,
    SourceCutIdentity,
)
from portfolio_common.domain.portfolio_source_observations import require_observation_identity
from portfolio_common.portfolio_financial_source_cut_admission import (
    ClosedInput,
    Count,
    Digest,
    ExpectedPopulationInput,
    FinancialInput,
    Identity,
    RegistryMemberInput,
    Revision,
)
from pydantic import (
    Field,
    field_validator,
    model_validator,
)


class CutAddress(ClosedInput):
    source_system: Identity
    registry_scope_id: Identity
    source_cut_id: Identity
    revision: Revision

    @field_validator("source_system", "registry_scope_id", "source_cut_id")
    @classmethod
    def exact_identity(cls, value: str) -> str:
        require_observation_identity(value, "source cut address")
        return value


class CutHeader(CutAddress):
    definition_version: Identity
    coverage_from: date
    coverage_to: date
    calendar: Identity
    observed_at: datetime
    generated_at: datetime
    predecessor_hash: Digest | None
    expected_head_hash: Digest | None

    def to_identity(self, tenant_id: str) -> SourceCutIdentity:
        return SourceCutIdentity(
            tenant_id=tenant_id,
            scope_id=self.registry_scope_id,
            **self.model_dump(include=set(CutHeader.model_fields) - {"registry_scope_id"}),
        )

    @model_validator(mode="after")
    def valid_declaration(self) -> Self:
        self.to_identity("validation-scope-only")
        return self


class RegistryChunkInput(CutAddress):
    chunk_index: Count
    members: tuple[RegistryMemberInput, ...] = Field(max_length=500)
    typed_content_hash: Digest

    @model_validator(mode="after")
    def typed_root_matches(self) -> Self:
        expected = canonical_content_hash(
            {
                "contract": "PortfolioHistoricalRegistryChunk:v1",
                "members": [d.to_domain().content_hash for d in self.members],
            }
        )
        if self.typed_content_hash != expected:
            raise ValueError("registry chunk typed hash mismatch")
        return self


class RegistrySealInput(CutHeader):
    expected_population: ExpectedPopulationInput
    declared_coverage: DeclaredCoverage
    supplied_count: Count
    members_root: Digest
    chunk_count: Count
    chunks_root: Digest

    def header(self) -> CutHeader:
        return cast(
            CutHeader,
            CutHeader.model_validate(self.model_dump(include=set(CutHeader.model_fields))),
        )

    def to_domain(self, tenant_id: str) -> HistoricalRegistryCut:
        return HistoricalRegistryCut(
            self.header().to_identity(tenant_id),
            self.expected_population.to_domain(),
            self.declared_coverage,
            self.supplied_count,
            self.members_root,
            self.chunk_count,
            self.chunks_root,
        )


class FinancialChunkInput(CutAddress):
    chunk_index: Count
    selections: tuple[FinancialInput, ...] = Field(max_length=500)
    typed_content_hash: Digest

    @model_validator(mode="after")
    def typed_root_matches(self) -> Self:
        expected = canonical_content_hash(
            {
                "contract": "PortfolioFinancialSourceCutChunk:v1",
                "selections": [s.model_dump(mode="json") for s in self.selections],
            }
        )
        if self.typed_content_hash != expected:
            raise ValueError("financial chunk typed hash mismatch")
        return self


class FinancialSealInput(CutHeader):
    selection_count: Count
    selections_root: Digest
    chunk_count: Count
    chunks_root: Digest

    def header(self) -> CutHeader:
        return cast(
            CutHeader,
            CutHeader.model_validate(self.model_dump(include=set(CutHeader.model_fields))),
        )

    def to_domain(self, tenant_id: str) -> FinancialSourceCutManifest:
        return FinancialSourceCutManifest(
            self.header().to_identity(tenant_id),
            self.selection_count,
            self.selections_root,
            self.chunk_count,
            self.chunks_root,
        )
