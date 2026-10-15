"""Immutable producer-declared flow evidence; never financial booking or eligibility."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from .calculation_lineage import canonical_content_hash, require_sha256_digest
from .portfolio_source_observations import (
    CashAvailabilityObservation,
    ObservationCoverage,
    ObservationEnvelope,
    ObservationFamily,
    require_observation_identity,
)

CLASSIFICATIONS = frozenset({"EXTERNAL_CASH", "INTERNAL_TRANSFER", "REVERSAL", "IN_KIND"})
POSTING_STATES = frozenset({"POSTED", "CANCELLED", "UNKNOWN"})
REVERSAL_STATES = frozenset({"NONE", "REVERSES", "UNKNOWN"})


@dataclass(frozen=True, slots=True)
class FlowEventObservation:
    envelope: ObservationEnvelope
    business_date: date
    currency: str
    amount: Decimal
    classification: str
    posting_state: str
    reversal_state: str
    reverses_source_record_id: str | None
    reversal_target: FlowEventPin | None
    economic_event_id: str | None = None
    transaction_id: str | None = None

    def __post_init__(self) -> None:
        # Reuse the existing exact NUMERIC/currency policy without deriving cash.
        if self.amount is None:
            raise ValueError("explicit exact flow amount required")
        amount = CashAvailabilityObservation(self.envelope, self.currency, self.amount, None, None)
        object.__setattr__(self, "amount", amount.settled)
        if type(self.business_date) is not date or not self.envelope.is_effective(
            self.business_date
        ):
            raise ValueError("flow business date must be within its declared effective interval")
        if self.classification not in CLASSIFICATIONS or self.posting_state not in POSTING_STATES:
            raise ValueError("explicit flow classification and posting state required")
        if self.reversal_state not in REVERSAL_STATES:
            raise ValueError("explicit reversal declaration required")
        for value in (self.reverses_source_record_id, self.economic_event_id, self.transaction_id):
            if value is not None:
                require_observation_identity(value, "flow reference")
        reverses = self.reversal_state == "REVERSES"
        if reverses != (self.reverses_source_record_id is not None):
            raise ValueError("reversal declaration and target disagree")
        if reverses != (self.reversal_target is not None):
            raise ValueError("reversal requires an explicit immutable target pin")
        if self.reversal_target is not None and (
            not isinstance(self.reversal_target, FlowEventPin)
            or self.reversal_target.source_record_id != self.reverses_source_record_id
        ):
            raise ValueError("reversal target pin and event identity disagree")
        if (self.classification == "REVERSAL") != reverses:
            raise ValueError("reversal classification requires explicit reversal target")
        if self.reverses_source_record_id == self.envelope.source_record_id:
            raise ValueError("flow cannot reverse itself")

    @property
    def family(self) -> ObservationFamily:
        return ObservationFamily.FLOW_EVENT

    @property
    def content_hash(self) -> str:
        return canonical_content_hash(
            {"contract": "PortfolioFlowEventObservation:v1", "observation": asdict(self)}
        )

    @property
    def usable(self) -> bool:
        return (
            self.posting_state != "UNKNOWN"
            and self.reversal_state != "UNKNOWN"
            and self.envelope.coverage is ObservationCoverage.COMPLETE
        )


@dataclass(frozen=True, slots=True)
class FlowEventPin:
    source_record_id: str
    observation_id: str
    content_hash: str
    flow_source_record_revision: int

    def __post_init__(self) -> None:
        require_observation_identity(self.source_record_id, "source_record_id")
        require_sha256_digest(self.observation_id, "observation_id")
        require_sha256_digest(self.content_hash, "content_hash")
        if (
            self.observation_id != self.content_hash
            or type(self.flow_source_record_revision) is not int
        ):
            raise ValueError("exact typed event pins required")
        if self.flow_source_record_revision < 1:
            raise ValueError("positive source version required")


@dataclass(frozen=True, slots=True)
class FlowSourceCut:
    tenant_id: str
    portfolio_id: str
    source_system: str
    source_cut_id: str
    cut_revision: int
    definition_version: str
    currency: str
    coverage_from: date
    coverage_to: date
    coverage: ObservationCoverage
    event_pins: tuple[FlowEventPin, ...]
    dependency_pins: tuple[FlowEventPin, ...]
    predecessor_cut_hash: str | None
    expected_head_hash: str | None

    def __post_init__(self) -> None:
        for name in (
            "tenant_id",
            "portfolio_id",
            "source_system",
            "source_cut_id",
            "definition_version",
        ):
            require_observation_identity(getattr(self, name), name)
        if type(self.cut_revision) is not int or self.cut_revision < 1:
            raise ValueError("positive cut revision required")
        if (
            type(self.coverage_from) is not date
            or type(self.coverage_to) is not date
            or self.coverage_from > self.coverage_to
        ):
            raise ValueError("ordered inclusive coverage window required")
        if (
            len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isalpha()
            or not self.currency.isupper()
        ):
            raise ValueError("canonical currency required")
        if not isinstance(self.coverage, ObservationCoverage) or type(self.event_pins) is not tuple:
            raise ValueError("typed coverage and immutable event pins required")
        if len(self.event_pins) > 1000 or any(
            not isinstance(p, FlowEventPin) for p in self.event_pins
        ):
            raise ValueError("bounded typed event set required")
        ids = [p.source_record_id for p in self.event_pins]
        if ids != sorted(set(ids)):
            raise ValueError("event pins must be uniquely ordered by source_record_id")
        if type(self.dependency_pins) is not tuple or any(
            not isinstance(p, FlowEventPin) for p in self.dependency_pins
        ):
            raise ValueError("typed immutable reversal dependency pins required")
        dependencies = [
            (p.source_record_id, p.flow_source_record_revision, p.observation_id)
            for p in self.dependency_pins
        ]
        if dependencies != sorted(set(dependencies)):
            raise ValueError("dependency pins must be uniquely ordered")
        pins = self.event_pins + self.dependency_pins
        if len(pins) > 1000:
            raise ValueError("combined flow evidence exceeds bounded membership")
        if len({p.observation_id for p in pins}) != len(pins) or len(
            {(p.source_record_id, p.flow_source_record_revision) for p in pins}
        ) != len(pins):
            raise ValueError("duplicate immutable flow pin")
        if self.cut_revision == 1:
            if self.predecessor_cut_hash is not None or self.expected_head_hash is not None:
                raise ValueError("original cut cannot name predecessor")
        else:
            for value in (self.predecessor_cut_hash, self.expected_head_hash):
                if value is None:
                    raise ValueError("cut predecessor required")
                require_sha256_digest(value, "cut predecessor")
            if self.predecessor_cut_hash != self.expected_head_hash:
                raise ValueError("cut predecessor must equal expected head")

    @property
    def content_hash(self) -> str:
        return canonical_content_hash(
            {"contract": "PortfolioFlowSourceCut:v1", "cut": asdict(self)}
        )

    @property
    def chain_key(self) -> tuple[str, str, str, str]:
        return self.tenant_id, self.portfolio_id, self.source_system, self.source_cut_id


def require_flow_target(
    owner: FlowEventObservation, target: FlowEventObservation, pin: FlowEventPin
) -> None:
    """An explicit immutable target may be outside the flow window, never in the future."""
    left, right = owner.envelope, target.envelope
    if (
        (
            left.tenant_id,
            left.portfolio_id,
            left.producer_id,
            owner.currency,
            left.definition_version,
        )
        != (
            right.tenant_id,
            right.portfolio_id,
            right.producer_id,
            target.currency,
            right.definition_version,
        )
        or pin.source_record_id != right.source_record_id
        or pin.flow_source_record_revision != right.source_revision
        or pin.observation_id != target.content_hash
        or pin.content_hash != target.content_hash
        or target.business_date > owner.business_date
    ):
        raise ValueError("reversal target scope, immutable pin or chronology mismatch")


def require_flow_cut_events(
    cut: FlowSourceCut,
    events: tuple[FlowEventObservation, ...],
    dependencies: tuple[FlowEventObservation, ...] = (),
) -> bool:
    """Validate window membership separately from exact retained reversal closure."""
    if len(events) != len(cut.event_pins) or len(dependencies) != len(cut.dependency_pins):
        raise ValueError("cut event or dependency set is incomplete")
    all_facts = events + dependencies
    by_observation = {f.content_hash: f for f in all_facts}
    if len(by_observation) != len(all_facts):
        raise ValueError("duplicate retained flow fact")
    for pins, facts, window_member in (
        (cut.event_pins, events, True),
        (cut.dependency_pins, dependencies, False),
    ):
        group = {f.content_hash: f for f in facts}
        for pin in pins:
            fact = group.get(pin.observation_id)
            if fact is None:
                raise ValueError("cut immutable pin missing")
            envelope = fact.envelope
            if (
                (envelope.tenant_id, envelope.portfolio_id, envelope.producer_id)
                != (cut.tenant_id, cut.portfolio_id, cut.source_system)
                or fact.currency != cut.currency
                or envelope.definition_version != cut.definition_version
                or pin.source_record_id != envelope.source_record_id
                or fact.content_hash != pin.content_hash
                or envelope.source_revision != pin.flow_source_record_revision
                or (
                    window_member and not cut.coverage_from <= fact.business_date <= cut.coverage_to
                )
            ):
                raise ValueError("cut event scope or pin mismatch")
    needed = set()
    dependency_ids = {p.observation_id for p in cut.dependency_pins}
    for fact in events:
        seen = {fact.envelope.source_record_id}
        current = fact
        while current.reversal_target is not None:
            pin = current.reversal_target
            target = by_observation.get(pin.observation_id)
            if target is None:
                raise ValueError("reversal target dependency missing")
            require_flow_target(current, target, pin)
            if target.envelope.source_record_id in seen:
                raise ValueError("reversal cycle")
            seen.add(target.envelope.source_record_id)
            if pin.observation_id in dependency_ids:
                needed.add(pin.observation_id)
            current = target
    if needed != dependency_ids:
        raise ValueError("unreferenced reversal dependency")
    return cut.coverage is ObservationCoverage.COMPLETE and all(f.usable for f in all_facts)
