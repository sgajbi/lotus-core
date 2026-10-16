"""Closed JSON transport reconstruction into framework-independent source declarations."""

import json
from copy import deepcopy
from datetime import date, datetime

from pydantic import ConfigDict, TypeAdapter
from pydantic_core import core_schema

from .domain.portfolio_financial_source_cuts import (
    CompatibilityDeclaration,
    DeclaredCoverage,
    EffectiveDeclaration,
    ExpectedPopulation,
    FinancialSourceCut,
    FinancialSourceCutManifest,
    HistoricalRegistryCut,
    HistoricalRegistryMember,
    InputRole,
    ProductSelection,
    SettledUnencumberedDeclaration,
    SourceCutIdentity,
)
from .portfolio_financial_source_cut_admission import (
    CashSemanticInput,
    ClosedInput,
    CompatibilityInput,
    Count,
    Digest,
    ExpectedPopulationInput,
    Revision,
)


class ClosedSourceDeclaration:
    """Explicit QCP transport policy for neutral domain instances and their JSON shape.

    Build an independent schema so framework policy never mutates the domain classes or
    another caller's adapter. The same core policy enforces validation and emits the closed
    response schema, including nested declarations. Python input retains strict instance
    semantics; JSON reconstruction still runs each domain constructor's validators.
    """

    _types = frozenset(
        {
            SourceCutIdentity,
            EffectiveDeclaration,
            ExpectedPopulation,
            HistoricalRegistryMember,
            HistoricalRegistryCut,
            FinancialSourceCutManifest,
            ProductSelection,
            SettledUnencumberedDeclaration,
            CompatibilityDeclaration,
            FinancialSourceCut,
        }
    )

    @classmethod
    def __get_pydantic_core_schema__(cls, source, _handler):
        if source not in cls._types:
            raise TypeError("neutral source declaration transport type required")
        schema = deepcopy(TypeAdapter(source).core_schema)
        cls._close(schema)
        return schema

    @classmethod
    def _close(cls, schema):
        if isinstance(schema, dict):
            if schema.get("type") == "dataclass" and schema.get("cls") in cls._types:
                schema["config"] = core_schema.CoreConfig(
                    **schema.get("config", {}), extra_fields_behavior="forbid", strict=True
                )
                schema.setdefault("metadata", {}).setdefault("pydantic_js_functions", []).append(
                    cls._closed_json_schema
                )
            for value in schema.values():
                cls._close(value)
        elif isinstance(schema, list):
            for value in schema:
                cls._close(value)

    @staticmethod
    def _closed_json_schema(schema, handler):
        result = handler(schema)
        # Pydantic's vanilla dataclass JSON generator reads class metadata rather than
        # CoreConfig. Publish the actual transport validator's policy without adding
        # framework attributes to the domain class.
        if schema["config"]["extra_fields_behavior"] == "forbid":
            handler.resolve_ref_schema(result)["additionalProperties"] = False
        return result


class SourceCutIdentityInput(ClosedInput):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    tenant_id: str
    source_system: str
    scope_id: str
    source_cut_id: str
    revision: Revision
    definition_version: str
    coverage_from: date
    coverage_to: date
    calendar: str
    observed_at: datetime
    generated_at: datetime
    predecessor_hash: Digest | None
    expected_head_hash: Digest | None

    def to_domain(self) -> SourceCutIdentity:
        return SourceCutIdentity(**self.model_dump())


class HistoricalRegistryCutInput(ClosedInput):
    identity: SourceCutIdentityInput
    expected_population: ExpectedPopulationInput
    declared_coverage: DeclaredCoverage
    supplied_count: Count
    members_root: Digest
    chunk_count: Count
    chunks_root: Digest

    def to_domain(self) -> HistoricalRegistryCut:
        return HistoricalRegistryCut(
            **self.model_dump(exclude={"identity", "expected_population"}),
            identity=self.identity.to_domain(),
            expected_population=self.expected_population.to_domain(),
        )


class FinancialSourceCutManifestInput(ClosedInput):
    identity: SourceCutIdentityInput
    selection_count: Count
    selections_root: Digest
    chunk_count: Count
    chunks_root: Digest

    def to_domain(self) -> FinancialSourceCutManifest:
        return FinancialSourceCutManifest(
            **self.model_dump(exclude={"identity"}), identity=self.identity.to_domain()
        )


class RetainedProductSelectionInput(ClosedInput):
    role: InputRole
    product_name: str
    product_version: str
    selector_hash: Digest
    content_hash: Digest
    receipt_job_id: str
    source_revision: str

    def to_domain(self) -> ProductSelection:
        return ProductSelection(**self.model_dump())


class RetainedFinancialSourceCutInput(ClosedInput):
    """Retained graph references omit the ingress-only native selector payloads."""

    identity: SourceCutIdentityInput
    portfolio_id: str
    currency: str
    prior_date: date
    month_end_date: date
    registry_root: Digest
    member_revision: Revision
    selections: tuple[RetainedProductSelectionInput, ...]
    settled_unencumbered: CashSemanticInput | None
    compatibility: CompatibilityInput | None

    def to_domain(self) -> FinancialSourceCut:
        return FinancialSourceCut(
            **self.model_dump(
                exclude={"identity", "selections", "settled_unencumbered", "compatibility"}
            ),
            identity=self.identity.to_domain(),
            selections=tuple(selection.to_domain() for selection in self.selections),
            settled_unencumbered=(
                None if self.settled_unencumbered is None else self.settled_unencumbered.to_domain()
            ),
            compatibility=None if self.compatibility is None else self.compatibility.to_domain(),
        )


def retained_financial_cut_from_payload(payload) -> FinancialSourceCut:
    return RetainedFinancialSourceCutInput.model_validate_json(
        json.dumps(payload, allow_nan=False), strict=True
    ).to_domain()


def source_manifest_from_payload(payload, tenant, product):
    models: dict[str, type[HistoricalRegistryCutInput] | type[FinancialSourceCutManifestInput]] = {
        "PortfolioHistoricalRegistry": HistoricalRegistryCutInput,
        "PortfolioFinancialSourceCut": FinancialSourceCutManifestInput,
    }
    if type(payload) is not dict or product not in models:
        raise ValueError("closed supported source manifest required")
    body = dict(payload)
    try:
        identity = {
            name: body.pop(name)
            for name in SourceCutIdentityInput.model_fields
            if name not in {"tenant_id", "scope_id"}
        }
        identity.update(tenant_id=tenant, scope_id=body.pop("registry_scope_id"))
    except KeyError as error:
        raise ValueError("complete source manifest identity required") from error
    return (
        models[product]
        .model_validate_json(
            json.dumps(dict(identity=identity, **body), allow_nan=False), strict=True
        )
        .to_domain()
    )
