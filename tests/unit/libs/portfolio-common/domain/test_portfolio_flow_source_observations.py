"""Explicit state matrix, exact financial source facts and complete membership."""

from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from itertools import product

import pytest
from portfolio_common.domain.portfolio_flow_source_observations import (
    require_flow_cut_events,
)
from portfolio_common.domain.portfolio_source_observations import (
    ObservationCoverage,
)

from tests.test_support.portfolio_flow_source_fixtures import cut, dated_event, event, pin

pytestmark = [pytest.mark.unit, pytest.mark.domain]


@pytest.mark.parametrize(
    "classification,posting,reversal,target",
    list(
        product(
            ("EXTERNAL_CASH", "INTERNAL_TRANSFER", "REVERSAL", "IN_KIND"),
            ("POSTED", "CANCELLED", "UNKNOWN"),
            ("NONE", "REVERSES", "UNKNOWN"),
            (None, "original"),
        )
    ),
)
def test_exhaustive_explicit_state_matrix(classification, posting, reversal, target):
    valid = (reversal == "REVERSES") == (target is not None) and (classification == "REVERSAL") == (
        reversal == "REVERSES"
    )
    kwargs = dict(
        classification=classification,
        posting_state=posting,
        reversal_state=reversal,
        reverses_source_record_id=target,
        reversal_target=pin(event("original"))
        if reversal == "REVERSES" and target is not None
        else None,
    )
    if not valid:
        with pytest.raises(ValueError):
            event(**kwargs)
    else:
        fact = event(**kwargs)
        assert fact.usable == (posting != "UNKNOWN" and reversal != "UNKNOWN")


@pytest.mark.parametrize(
    "amount",
    [
        None,
        1.5,
        "1.5",
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("1E-16384"),
        Decimal("1E131072"),
    ],
)
def test_inexact_nonfinite_missing_and_unrepresentable_amounts_refused(amount):
    with pytest.raises((ValueError, TypeError)):
        event(amount=amount)


def test_source_identity_is_stable_and_amount_is_exact_under_hostile_context():
    with localcontext() as context:
        context.prec = 2
        fact = event()
        assert str(fact.amount) == "10.001000000000000000001"
        assert fact.envelope.source_record_id == "source-event"
        assert replace(fact, amount=Decimal("0")).envelope.source_record_id == "source-event"
        assert event(amount=Decimal("-1000.03")).amount == Decimal("-1000.03")
        assert len(fact.content_hash) == 64


def test_complete_empty_is_observed_but_partial_and_missing_are_unavailable():
    assert require_flow_cut_events(cut(), ())
    for coverage in (ObservationCoverage.PARTIAL, ObservationCoverage.MISSING):
        assert not require_flow_cut_events(cut(coverage=coverage), ())
    fact = event(posting_state="UNKNOWN")
    assert not require_flow_cut_events(cut(fact), (fact,))


def test_manifest_exact_scope_version_hash_and_definition_required():
    fact = event()
    manifest = cut(fact)
    for mutation in (
        replace(fact, currency="USD"),
        replace(fact, amount=Decimal("20")),
        replace(fact, envelope=replace(fact.envelope, tenant_id="foreign")),
        replace(fact, envelope=replace(fact.envelope, definition_version="v2")),
    ):
        with pytest.raises(ValueError):
            require_flow_cut_events(manifest, (mutation,))
    for facts in ((), (fact, fact), (event("foreign"),)):
        with pytest.raises(ValueError):
            require_flow_cut_events(manifest, facts)


def test_reversal_targets_cycles_self_and_duplicate_manifest_refused():
    original = event("a")
    reversal = event(
        "b",
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="a",
        reversal_target=pin(original),
    )
    assert require_flow_cut_events(cut(original, reversal), (reversal, original))
    with pytest.raises(ValueError, match="target"):
        require_flow_cut_events(cut(reversal), (reversal,))
    cycle = replace(
        original,
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="b",
        reversal_target=pin(reversal),
        envelope=replace(
            original.envelope,
            source_revision=2,
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    with pytest.raises(ValueError, match="cycle"):
        require_flow_cut_events(
            cut(cycle, reversal, dependency_pins=(pin(original),)), (cycle, reversal), (original,)
        )
    with pytest.raises(ValueError, match="itself"):
        event(
            "a",
            classification="REVERSAL",
            reversal_state="REVERSES",
            reverses_source_record_id="a",
            reversal_target=pin(original),
        )
    with pytest.raises(ValueError, match="ordered"):
        cut(event_pins=(cut(original).event_pins[0],) * 2)


def test_original_and_corrected_manifest_hashes_keep_exact_revision_pins():
    original = event()
    corrected = replace(
        original,
        posting_state="CANCELLED",
        envelope=replace(
            original.envelope,
            source_revision=2,
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    first = cut(original)
    second = cut(
        corrected,
        cut_revision=2,
        predecessor_cut_hash=first.content_hash,
        expected_head_hash=first.content_hash,
    )
    assert first.content_hash != second.content_hash
    assert require_flow_cut_events(first, (original,))
    assert require_flow_cut_events(second, (corrected,))
    with pytest.raises(ValueError):
        require_flow_cut_events(first, (corrected,))


@pytest.mark.parametrize("target_date", [date(2025, 12, 15), date(2026, 1, 1)])
def test_reversal_binds_exact_same_or_prior_window_target_without_adding_target_flow(target_date):
    target = dated_event("original", target_date, amount=Decimal("9000"))
    reversal = event(
        "reversal",
        amount=Decimal("-7.50"),
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="original",
        reversal_target=pin(target),
    )
    if target_date.month == 1:
        manifest = cut(target, reversal)
        assert require_flow_cut_events(manifest, (target, reversal))
    else:
        manifest = cut(reversal, dependency_pins=(pin(target),))
        assert require_flow_cut_events(manifest, (reversal,), (target,))
        assert (
            len(manifest.event_pins) == 1 and manifest.event_pins[0].source_record_id == "reversal"
        )
        assert manifest.dependency_pins[0].observation_id == target.content_hash


def test_multi_hop_closure_and_late_target_correction_keep_original_immutable_pin():
    november = dated_event("a", date(2025, 11, 15))
    december = dated_event(
        "b",
        date(2025, 12, 15),
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="a",
        reversal_target=pin(november),
    )
    january = event(
        "c",
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="b",
        reversal_target=pin(december),
    )
    manifest = cut(january, dependency_pins=(pin(november), pin(december)))
    assert require_flow_cut_events(manifest, (january,), (november, december))
    correction = replace(
        december,
        amount=Decimal("500"),
        envelope=replace(
            december.envelope,
            source_revision=2,
            predecessor_id=december.content_hash,
            expected_head_hash=december.content_hash,
        ),
    )
    assert require_flow_cut_events(manifest, (january,), (november, december))
    with pytest.raises(ValueError):
        require_flow_cut_events(manifest, (january,), (november, correction))
    with pytest.raises(ValueError, match="incomplete"):
        require_flow_cut_events(manifest, (january,), (december,))


@pytest.mark.parametrize(
    "mutation", ["foreign-tenant", "currency", "definition", "future", "hash", "version", "orphan"]
)
def test_unresolved_foreign_tampered_future_and_unreachable_dependencies_refuse(mutation):
    target = dated_event("target", date(2025, 12, 15))
    if mutation == "foreign-tenant":
        target = replace(target, envelope=replace(target.envelope, tenant_id="foreign"))
    if mutation == "currency":
        target = replace(target, currency="USD")
    if mutation == "definition":
        target = replace(target, envelope=replace(target.envelope, definition_version="v2"))
    if mutation == "future":
        target = dated_event("target", date(2026, 2, 1))
    target_pin = pin(target)
    if mutation == "hash":
        target_pin = replace(target_pin, observation_id="a" * 64, content_hash="a" * 64)
    if mutation == "version":
        target_pin = replace(target_pin, flow_source_record_revision=2)
    reversal = event(
        "reversal",
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="target",
        reversal_target=target_pin,
    )
    dependencies = (target,)
    pins = (pin(target),)
    if mutation == "orphan":
        orphan = dated_event("unreferenced", date(2025, 12, 1))
        dependencies += (orphan,)
        pins += (pin(orphan),)
    with pytest.raises(ValueError):
        require_flow_cut_events(cut(reversal, dependency_pins=pins), (reversal,), dependencies)


def test_explicit_target_pin_required_and_combined_membership_is_bounded():
    with pytest.raises(ValueError, match="immutable target"):
        event(
            "r", classification="REVERSAL", reversal_state="REVERSES", reverses_source_record_id="a"
        )
    with pytest.raises(ValueError, match="bounded"):
        cut(
            event("window"),
            dependency_pins=tuple(pin(event(f"dependency-{i:04}")) for i in range(1000)),
        )
