"""Neutral producer declarations; completeness is not financial or bank authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Iterable, Mapping

from .calculation_lineage import canonical_content_hash, require_sha256_digest
from .portfolio_source_cut_declarations import (
    ClosedNeutralDeclaration as ClosedNeutralDeclaration,
)
from .portfolio_source_cut_declarations import (
    DeclaredCoverage as DeclaredCoverage,
)
from .portfolio_source_cut_declarations import (
    EffectiveDeclaration as EffectiveDeclaration,
)
from .portfolio_source_cut_declarations import (
    ExpectedPopulation as ExpectedPopulation,
)
from .portfolio_source_cut_declarations import (
    HistoricalRegistryCut as HistoricalRegistryCut,
)
from .portfolio_source_cut_declarations import (
    HistoricalRegistryMember as HistoricalRegistryMember,
)
from .portfolio_source_cut_declarations import (
    SourceCutIdentity as SourceCutIdentity,
)
from .portfolio_source_cut_declarations import (
    ordered_dates as ordered_dates,
)
from .portfolio_source_cut_declarations import (
    positive_revision as positive_revision,
)
from .portfolio_source_cut_declarations import (
    require_currency as require_currency,
)
from .portfolio_source_observations import require_observation_identity


class InputRole(StrEnum):
    PRIOR_ASSETS = "PRIOR_ASSETS"
    MONTH_END_ASSETS = "MONTH_END_ASSETS"
    CASH = "CASH"
    READINESS = "READINESS"
    FLOWS = "FLOWS"


@dataclass(frozen=True, slots=True)
class ProductSelection(ClosedNeutralDeclaration):
    role: InputRole
    product_name: str
    product_version: str
    selector_hash: str
    content_hash: str
    receipt_job_id: str
    source_revision: str

    def __post_init__(self) -> None:
        allowed = {
            InputRole.PRIOR_ASSETS: {"PortfolioTimeseriesInput"},
            InputRole.MONTH_END_ASSETS: {"PortfolioTimeseriesInput"},
            InputRole.CASH: {"PortfolioFinancialSourceObservations"},
            InputRole.READINESS: {"PortfolioFinancialSourceObservations"},
            InputRole.FLOWS: {"PortfolioFinancialFlowObservations"},
        }
        if not isinstance(self.role, InputRole) or self.product_name not in allowed[self.role]:
            raise ValueError("exact role and source product family required")
        for digest in (self.selector_hash, self.content_hash):
            require_sha256_digest(digest, "source selection")
        for value in (self.product_version, self.receipt_job_id, self.source_revision):
            require_observation_identity(value, "exact product version/receipt")


@dataclass(frozen=True, slots=True)
class SettledUnencumberedDeclaration(ClosedNeutralDeclaration):
    amount: Decimal | None
    currency: str
    business_date: date
    semantic_definition: str
    producer_revision: str

    def __post_init__(self) -> None:
        # Reuse the exact existing amount policy; never derive this from another cash field.
        from .financial.precision import EXACT_UNBOUNDED
        from .portfolio_source_observations import _canonical_cash_amount

        if self.amount is not None:
            EXACT_UNBOUNDED.require_exact(self.amount, field_name="settled_unencumbered_amount")
            object.__setattr__(
                self, "amount", _canonical_cash_amount(self.amount, "settled_unencumbered_amount")
            )
        if type(self.business_date) is not date:
            raise ValueError("explicit cash declaration date required")
        for value in (self.semantic_definition, self.producer_revision):
            require_observation_identity(value, "cash declaration provenance")
        if (
            len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isalpha()
            or not self.currency.isupper()
        ):
            raise ValueError("explicit cash declaration currency required")


class OrderedContentRoot:
    """Incremental ordered hashing for synchronous and asynchronous source readers."""

    def __init__(self, contract: str, *, checkpoint: tuple[str, int, str] | None = None):
        require_observation_identity(contract, "ordered root contract")
        self._contract = contract
        self._state = hashlib.sha256((contract + "\0").encode()).digest()
        self.count = 0
        if checkpoint is not None:
            saved_contract, count, state = checkpoint
            if saved_contract != contract or type(count) is not int or count < 0:
                raise ValueError("exact nonnegative root checkpoint count required")
            require_sha256_digest(state, "root checkpoint state")
            self.count, self._state = count, bytes.fromhex(state)

    def append(self, item: str) -> None:
        require_sha256_digest(item, "ordered item")
        self._state = hashlib.sha256(self._state + bytes.fromhex(item)).digest()
        self.count += 1

    def finish(self) -> tuple[int, str]:
        return self.count, hashlib.sha256(
            self._state + b"\0" + str(self.count).encode("ascii")
        ).hexdigest()

    @property
    def checkpoint(self) -> tuple[str, int, str]:
        return self._contract, self.count, self._state.hex()


def ordered_content_root(contract: str, hashes: Iterable[str]) -> tuple[int, str]:
    """Stream a domain-separated ordered root without a total-population cap."""
    accumulator = OrderedContentRoot(contract)
    for item in hashes:
        accumulator.append(item)
    return accumulator.finish()


def source_product_bytes(payload: Mapping[str, object], *, serializer: str) -> bytes:
    """Deterministic acquired DTO bytes, never labeled original supplier wire bytes."""
    require_observation_identity(serializer, "source-capture serializer")
    # Adapter supplies its explicit JSON-mode DTO; nonfinite values cannot enter the wire.
    return json.dumps(
        {"serializer": serializer, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class FinancialSourceCutManifest(ClosedNeutralDeclaration):
    identity: SourceCutIdentity
    selection_count: int
    selections_root: str
    chunk_count: int
    chunks_root: str

    def __post_init__(self) -> None:
        if type(self.identity) is not SourceCutIdentity:
            raise ValueError("governed financial manifest identity required")
        SourceCutIdentity.__post_init__(self.identity)
        if any(type(n) is not int or n < 0 for n in (self.selection_count, self.chunk_count)):
            raise ValueError("exact nonnegative manifest counts required")
        if self.selection_count > 0 and self.chunk_count == 0:
            raise ValueError("nonempty manifest requires retained chunks")
        for digest in (self.selections_root, self.chunks_root):
            require_sha256_digest(digest, "financial batch manifest")

    @property
    def content_hash(self) -> str:
        return canonical_content_hash(
            {"contract": "PortfolioFinancialSourceCutManifest:v1", "manifest": asdict(self)}
        )


@dataclass(frozen=True, slots=True)
class CompatibilityDeclaration(ClosedNeutralDeclaration):
    source_system: str
    scope_id: str
    definition_version: str
    registry_root: str
    role_roots: tuple[tuple[InputRole, str], ...]
    coverage_from: date
    coverage_to: date
    currency: str
    basis_reference: str
    original_evidence_digest: str

    def __post_init__(self) -> None:
        for value in (
            self.source_system,
            self.scope_id,
            self.definition_version,
            self.basis_reference,
        ):
            require_observation_identity(value, "compatibility declaration")
        require_currency(self.currency)
        ordered_dates(self.coverage_from, self.coverage_to)
        if (
            type(self.role_roots) is not tuple
            or any(
                type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not InputRole
                for pair in self.role_roots
            )
            or tuple(role for role, _ in self.role_roots) != tuple(InputRole)
        ):
            raise ValueError("exact canonical five-role compatibility inventory required")
        for digest in (
            self.registry_root,
            self.original_evidence_digest,
            *(root for _, root in self.role_roots),
        ):
            require_sha256_digest(digest, "compatibility evidence")

    @property
    def posture(self) -> str:
        return "DECLARED_UNVERIFIED"


@dataclass(frozen=True, slots=True)
class FinancialSourceCut(ClosedNeutralDeclaration):
    identity: SourceCutIdentity
    portfolio_id: str
    currency: str
    prior_date: date
    month_end_date: date
    registry_root: str
    member_revision: int
    selections: tuple[ProductSelection, ...]
    settled_unencumbered: SettledUnencumberedDeclaration | None
    compatibility: CompatibilityDeclaration | None

    def __post_init__(self) -> None:
        if type(self.identity) is not SourceCutIdentity:
            raise ValueError("typed cut identity required")
        SourceCutIdentity.__post_init__(self.identity)
        require_observation_identity(self.portfolio_id, "portfolio_id")
        require_currency(self.currency)
        ordered_dates(self.prior_date, self.month_end_date, exclusive=True)
        positive_revision(self.member_revision)
        require_sha256_digest(self.registry_root, "registry root")
        if (
            type(self.selections) is not tuple
            or any(type(s) is not ProductSelection for s in self.selections)
            or tuple(selection.role for selection in self.selections) != tuple(InputRole)
        ):
            raise ValueError("exact ordered five product selections required")
        for selection in self.selections:
            ProductSelection.__post_init__(selection)
        if self.settled_unencumbered is not None:
            if type(self.settled_unencumbered) is not SettledUnencumberedDeclaration:
                raise ValueError("governed settled-unencumbered declaration required")
            SettledUnencumberedDeclaration.__post_init__(self.settled_unencumbered)
        if self.settled_unencumbered is not None and (
            self.settled_unencumbered.currency != self.currency
            or self.settled_unencumbered.business_date != self.month_end_date
        ):
            raise ValueError("cash semantic declaration date/currency mismatch")
        if self.compatibility is not None:
            if type(self.compatibility) is not CompatibilityDeclaration:
                raise ValueError("governed compatibility declaration required")
            CompatibilityDeclaration.__post_init__(self.compatibility)
            expected_roots = tuple((s.role, s.content_hash) for s in self.selections)
            declaration = self.compatibility
            if (
                declaration.registry_root != self.registry_root
                or declaration.role_roots != expected_roots
                or declaration.currency != self.currency
                or (declaration.coverage_from, declaration.coverage_to)
                != (self.identity.coverage_from, self.identity.coverage_to)
                or declaration.source_system != self.identity.source_system
                or declaration.scope_id != self.identity.scope_id
            ):
                raise ValueError("compatibility declaration must bind exact source scope and roots")

    @property
    def compatibility_posture(self) -> str:
        return "UNAVAILABLE" if self.compatibility is None else "DECLARED_UNVERIFIED"

    @property
    def content_hash(self) -> str:
        return canonical_content_hash(
            {"contract": "PortfolioFinancialSourceCut:v1", "cut": asdict(self)}
        )
