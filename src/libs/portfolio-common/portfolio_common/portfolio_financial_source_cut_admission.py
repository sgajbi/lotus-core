"""Exact registry-scoped authority and bounded chunk admission, separate from fact grants."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Iterable, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from .domain.calculation_lineage import canonical_content_hash, require_sha256_digest
from .domain.portfolio_financial_source_cuts import (
    CompatibilityDeclaration,
    EffectiveDeclaration,
    ExpectedPopulation,
    FinancialSourceCut,
    HistoricalRegistryMember,
    InputRole,
    ProductSelection,
    SettledUnencumberedDeclaration,
    SourceCutIdentity,
    ordered_content_root,
)
from .domain.portfolio_source_observations import require_observation_identity

PRODUCTS = frozenset({"PortfolioHistoricalRegistry", "PortfolioFinancialSourceCut"})
MAX_CHUNK_ROWS = 500
MAX_CHUNK_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class RegistrySourceGrant:
    tenant_id: str
    source_system: str
    registry_scope_id: str
    products: frozenset[str]

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.source_system, self.registry_scope_id):
            require_observation_identity(value, "exact registry grant")
            if "*" in value:
                raise ValueError("registry grants cannot use wildcards")
        if (
            type(self.products) is not frozenset
            or not self.products
            or not self.products <= PRODUCTS
        ):
            raise ValueError("explicit supported registry products required")


def parse_registry_source_grants(raw: str) -> tuple[RegistrySourceGrant, ...]:
    """New closed JSON shape; never fall back to the existing four-field fact parser."""
    if type(raw) is not str or len(raw.encode("utf-8")) > 65_536:
        raise ValueError("bounded typed registry grant configuration required")
    rows = closed_source_json(raw or "[]")
    if type(rows) is not list:
        raise ValueError("registry grant list required")
    result = []
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != {
            "tenant_id",
            "source_system",
            "registry_scope_id",
            "products",
        }:
            raise ValueError("closed registry grant shape required")
        products = row["products"]
        if (
            type(products) is not list
            or any(type(p) is not str for p in products)
            or len(set(products)) != len(products)
        ):
            raise ValueError("unique product list required")
        grant = RegistrySourceGrant(
            row["tenant_id"], row["source_system"], row["registry_scope_id"], frozenset(products)
        )
        key = (grant.tenant_id, grant.source_system, grant.registry_scope_id)
        if key in seen:
            raise ValueError("duplicate registry grant scope")
        seen.add(key)
        result.append(grant)
    return tuple(result)


def require_registry_source_grant(
    grants: Iterable[RegistrySourceGrant],
    *,
    tenant_id: str,
    source_system: str,
    registry_scope_id: str,
    product: str,
) -> None:
    admitted = False
    for grant in grants:
        if type(grant) is not RegistrySourceGrant:
            raise PermissionError("governed registry grant required")
        RegistrySourceGrant.__post_init__(grant)
        admitted |= (grant.tenant_id, grant.source_system, grant.registry_scope_id) == (
            tenant_id,
            source_system,
            registry_scope_id,
        ) and product in grant.products
    if product not in PRODUCTS or not admitted:
        raise PermissionError("exact tenant/producer/registry product grant required")


def require_chunk_budget(raw: bytes, row_count: int) -> str:
    if type(raw) is not bytes or not raw or len(raw) > MAX_CHUNK_BYTES:
        raise ValueError("nonempty bounded uncompressed chunk bytes required")
    if type(row_count) is not int or not 0 <= row_count <= MAX_CHUNK_ROWS:
        raise ValueError("bounded exact page row count required")
    return hashlib.sha256(raw).hexdigest()


def registry_member_root(members: Iterable[HistoricalRegistryMember]) -> tuple[int, str]:
    """One ordered pass; DB chunk/member indexes enforce cross-chunk uniqueness."""

    def hashes():
        previous = None
        for member in members:
            if type(member) is not HistoricalRegistryMember:
                raise ValueError("typed registry members required")
            HistoricalRegistryMember.__post_init__(member)
            key = (member.provider_namespace, member.source_member_id)
            if previous is not None and key <= previous:
                raise ValueError("strict canonical unique member order required")
            previous = key
            yield member.content_hash

    return ordered_content_root("PortfolioHistoricalRegistryMembers:v1", hashes())


def require_exact_replay(
    existing_typed_hash: str, existing_raw_hash: str, *, typed_hash: str, raw_hash: str
) -> None:
    for digest in (existing_typed_hash, existing_raw_hash, typed_hash, raw_hash):
        require_sha256_digest(digest, "immutable chunk replay")
    if (existing_typed_hash, existing_raw_hash) != (typed_hash, raw_hash):
        raise ValueError("divergent typed or raw chunk replay")


def closed_source_json(raw: str | bytes):
    """Refuse duplicate/nonfinite source keys before typed normalization hides them."""

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate neutral source field")
            value[key] = item
        return value

    def nonfinite(_):
        raise ValueError("nonfinite neutral source JSON")

    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except RecursionError as error:
        raise ValueError("neutral source JSON nesting exceeds the parser limit") from error


def registry_member_from_payload(payload) -> HistoricalRegistryMember:
    return RegistryMemberInput.model_validate_json(
        json.dumps(payload, allow_nan=False), strict=True
    ).to_domain()


def financial_input_from_payload(identity: SourceCutIdentity, payload) -> FinancialSourceCut:
    from .portfolio_financial_source_cut_decoding import retained_financial_cut_from_payload

    value = dict(payload)
    selections = []
    for source in value["selections"]:
        record = dict(source)
        selector = record.pop("selector")
        if canonical_content_hash(selector) != record["selector_hash"]:
            raise ValueError("retained selector typed drift")
        selections.append(record)
    value["selections"] = selections
    # JSON transport conversion belongs here, rather than in pure domain declarations.
    value["identity"] = {
        name: item.isoformat() if isinstance(item, (date,)) else item
        for name, item in asdict(identity).items()
    }
    return retained_financial_cut_from_payload(value)


Digest = Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


Identity = Annotated[str, Field(min_length=1, max_length=128)]


Revision = Annotated[StrictInt, Field(ge=1)]


Count = Annotated[StrictInt, Field(ge=0)]


class ClosedInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EffectiveDeclarationInput(ClosedInput):
    effective_from: date
    effective_to: date | None
    definition_version: Identity
    provenance_reference: Identity
    currency: str = Field(pattern="^[A-Z]{3}$")
    discretionary: StrictBool | None
    included: StrictBool

    def to_domain(self) -> EffectiveDeclaration:
        return EffectiveDeclaration(**self.model_dump())


class RegistryMemberInput(ClosedInput):
    source_member_id: Identity
    provider_namespace: Identity
    core_portfolio_id: Identity | None
    member_revision: Revision
    declarations: tuple[EffectiveDeclarationInput, ...] = Field(min_length=1)

    def to_domain(self) -> HistoricalRegistryMember:
        return HistoricalRegistryMember(
            **self.model_dump(exclude={"declarations"}),
            declarations=tuple(d.to_domain() for d in self.declarations),
        )

    @model_validator(mode="after")
    def valid_history(self) -> Self:
        self.to_domain()
        return self


class ExpectedPopulationInput(ClosedInput):
    reference: Identity
    definition_version: Identity
    count: Count
    content_hash: Digest

    def to_domain(self) -> ExpectedPopulation:
        return ExpectedPopulation(**self.model_dump())


class ValuationSelector(ClosedInput):
    kind: Literal["VALUATION"]
    as_of_date: date
    from_date: date
    to_date: date
    reporting_currency: str = Field(pattern="^[A-Z]{3}$")
    consumer_system: Identity
    export_job_id: Identity | None
    export_content_hash: Digest | None
    refresh_of_job_id: Identity | None

    @model_validator(mode="after")
    def explicit_window_and_export(self) -> Self:
        if self.from_date > self.to_date or self.to_date > self.as_of_date:
            raise ValueError("exact bounded valuation window required")
        if (self.export_job_id is None) != (self.export_content_hash is None):
            raise ValueError("retained export job and content hash required together")
        if self.refresh_of_job_id is not None and self.export_job_id is None:
            raise ValueError("export correction requires exact retained job")
        return self


class ObservationSourceSelector(ClosedInput):
    kind: Literal["CASH", "READINESS"]
    as_of_date: date
    producer_id: Identity
    source_record_id: Identity
    observation_id: Digest
    content_hash: Digest
    source_cut_id: Identity
    source_version: Revision


class FlowSourceSelector(ClosedInput):
    kind: Literal["FLOWS"]
    source_system: Identity
    source_cut_id: Identity
    cut_revision: Revision
    manifest_hash: Digest
    from_date: date
    to_date: date
    currency: str = Field(pattern="^[A-Z]{3}$")

    @model_validator(mode="after")
    def ordered_window(self) -> Self:
        if self.from_date > self.to_date:
            raise ValueError("ordered flow selection window required")
        return self


NativeSelector = Annotated[
    ValuationSelector | ObservationSourceSelector | FlowSourceSelector, Field(discriminator="kind")
]


class ProductSelectionInput(ClosedInput):
    role: InputRole
    product_name: Identity
    product_version: Identity
    selector: NativeSelector
    selector_hash: Digest
    content_hash: Digest
    receipt_job_id: Identity
    source_revision: Identity

    def to_domain(self) -> ProductSelection:
        return ProductSelection(**self.model_dump(exclude={"selector"}))

    @model_validator(mode="after")
    def exact_source_selection(self) -> Self:
        self.to_domain()
        kind = self.selector.kind
        expected = (
            "VALUATION"
            if self.role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS)
            else self.role.value
        )
        if (
            kind != expected
            or canonical_content_hash(self.selector.model_dump(mode="json")) != self.selector_hash
        ):
            raise ValueError("exact role/typed selector hash required")
        return self


class CashSemanticInput(ClosedInput):
    amount: Decimal | None = Field(strict=True)
    currency: str = Field(pattern="^[A-Z]{3}$")
    business_date: date
    semantic_definition: Identity
    producer_revision: Identity

    @field_validator("amount", mode="before", json_schema_input_type=str | None)
    @classmethod
    def exact_decimal_text(cls, value):
        if value is not None and type(value) not in (str, Decimal):
            raise ValueError("explicit exact decimal text required")
        if type(value) is str:
            if value != value.strip():
                raise ValueError("exact decimal text cannot contain boundary whitespace")
            try:
                return Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("exact decimal text required") from exc
        return value

    @model_validator(mode="after")
    def semantic_amount(self) -> Self:
        self.to_domain()
        return self

    def to_domain(self) -> SettledUnencumberedDeclaration:
        return SettledUnencumberedDeclaration(**self.model_dump())


class CompatibilityInput(ClosedInput):
    source_system: Identity
    scope_id: Identity
    definition_version: Identity
    registry_root: Digest
    role_roots: tuple[tuple[InputRole, Digest], ...]
    coverage_from: date
    coverage_to: date
    currency: str = Field(pattern="^[A-Z]{3}$")
    basis_reference: Identity
    original_evidence_digest: Digest

    def to_domain(self) -> CompatibilityDeclaration:
        return CompatibilityDeclaration(**self.model_dump())


class FinancialInput(ClosedInput):
    portfolio_id: Identity
    currency: str = Field(pattern="^[A-Z]{3}$")
    prior_date: date
    month_end_date: date
    registry_root: Digest
    member_revision: Revision
    selections: tuple[ProductSelectionInput, ...] = Field(min_length=5, max_length=5)
    settled_unencumbered: CashSemanticInput | None
    compatibility: CompatibilityInput | None

    @model_validator(mode="after")
    def exact_role_dates(self) -> Self:
        if self.prior_date >= self.month_end_date or tuple(
            s.role for s in self.selections
        ) != tuple(InputRole):
            raise ValueError("ordered prior/end dates and canonical five roles required")
        for selection in self.selections:
            selector = selection.selector
            if isinstance(selector, ValuationSelector):
                expected = (
                    self.prior_date
                    if selection.role is InputRole.PRIOR_ASSETS
                    else self.month_end_date
                )
                if (
                    not selector.from_date <= expected <= selector.to_date
                    or selector.reporting_currency != self.currency
                ):
                    raise ValueError("valuation selection must cover its role date/currency")
            elif isinstance(selector, ObservationSourceSelector):
                if selector.as_of_date != self.month_end_date:
                    raise ValueError("observation role must match exact month end")
            elif selector.currency != self.currency or selector.to_date != self.month_end_date:
                raise ValueError("flow currency/window does not match financial selection")
        return self

    def to_domain(self, identity: SourceCutIdentity) -> FinancialSourceCut:
        return FinancialSourceCut(
            identity=identity,
            **self.model_dump(exclude={"selections", "settled_unencumbered", "compatibility"}),
            selections=tuple(s.to_domain() for s in self.selections),
            settled_unencumbered=None
            if self.settled_unencumbered is None
            else self.settled_unencumbered.to_domain(),
            compatibility=None if self.compatibility is None else self.compatibility.to_domain(),
        )
