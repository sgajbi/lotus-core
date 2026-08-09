"""Test source-owned corporate-action parent-manifest readiness."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from portfolio_common.domain.calculation_lineage import FinancialSourceReference

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)

CorporateActionEventChild = corporate_action.CorporateActionEventChild
CorporateActionEventGraphReason = corporate_action.CorporateActionEventGraphReason
CorporateActionManifestReadinessStatus = corporate_action.CorporateActionManifestReadinessStatus
CorporateActionManifestReason = corporate_action.CorporateActionManifestReason
CorporateActionParentManifest = corporate_action.CorporateActionParentManifest
evaluate_corporate_action_manifest_readiness = (
    corporate_action.evaluate_corporate_action_manifest_readiness
)


def _child(
    transaction_id: str,
    transaction_type: str,
    role: str,
    *,
    dependencies: tuple[str, ...] = (),
    instrument: str | None = None,
    source: str | None = None,
    target: str | None = None,
    sequence: int | None = None,
) -> CorporateActionEventChild:
    return CorporateActionEventChild(
        transaction_id=transaction_id,
        transaction_type=transaction_type,
        child_role=role,
        dependency_transaction_ids=dependencies,
        child_sequence_hint=sequence,
        instrument_id=instrument,
        source_instrument_id=source,
        target_instrument_id=target,
    )


def _children() -> tuple[CorporateActionEventChild, ...]:
    return (
        _child(
            "SOURCE",
            "DEMERGER_OUT",
            "SOURCE_POSITION_REDUCE",
            instrument="PARENT-SEC",
            source="PARENT-SEC",
        ),
        _child(
            "TARGET-A",
            "DEMERGER_IN",
            "TARGET_POSITION_ADD",
            dependencies=("SOURCE",),
            instrument="TARGET-SEC-A",
            source="PARENT-SEC",
            target="TARGET-SEC-A",
            sequence=1,
        ),
        _child(
            "TARGET-B",
            "DEMERGER_IN",
            "TARGET_POSITION_ADD",
            dependencies=("SOURCE",),
            instrument="TARGET-SEC-B",
            source="PARENT-SEC",
            target="TARGET-SEC-B",
            sequence=2,
        ),
        _child(
            "CASH",
            "CASH_CONSIDERATION",
            "CASH_CONSIDERATION",
            dependencies=("TARGET-A", "TARGET-B"),
        ),
    )


def _manifest(
    *,
    children: tuple[CorporateActionEventChild, ...] | None = None,
    complete: bool = True,
) -> CorporateActionParentManifest:
    return CorporateActionParentManifest(
        corporate_action_event_id="CA-EVENT-001",
        portfolio_id="PB-SG-GLOBAL-001",
        linked_transaction_group_id="CA-GROUP-001",
        parent_event_reference="UPSTREAM-CA-001",
        corporate_action_type="DEMERGER",
        version=1,
        completion_declared=complete,
        expected_children=children if children is not None else _children(),
        source_reference=FinancialSourceReference(
            source_system="custodian-ca",
            source_record_id="CA-EVENT-001",
            source_revision="17",
            source_content_hash="a" * 64,
            observed_at=datetime(2026, 8, 9, 1, 0, tzinfo=UTC),
        ),
    )


def test_manifest_is_required_before_business_readiness() -> None:
    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=None,
        observed_children=(),
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.AWAITING_MANIFEST
    assert readiness.findings[0].reason == CorporateActionManifestReason.MANIFEST_REQUIRED


def test_manifest_requires_source_declared_completion() -> None:
    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(complete=False),
        observed_children=_children(),
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.AWAITING_COMPLETION
    assert readiness.ordered_children == ()


def test_manifest_rejects_lone_target_without_source_dependency() -> None:
    target = _child(
        "TARGET",
        "SPIN_IN",
        "TARGET_POSITION_ADD",
        instrument="TARGET-SEC",
        source="PARENT-SEC",
        target="TARGET-SEC",
    )

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=(target,)),
        observed_children=(target,),
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert CorporateActionManifestReason.CHILD_TYPE_NOT_ALLOWED in {
        finding.reason for finding in readiness.findings
    }


def test_manifest_validates_every_target_in_one_to_many_event() -> None:
    children = _children()
    malformed_second_target = replace(children[2], dependency_transaction_ids=("TARGET-A",))
    candidate = (children[0], children[1], malformed_second_target, children[3])

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=candidate),
        observed_children=candidate,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert readiness.findings[-1].reason == (
        CorporateActionManifestReason.TARGET_SOURCE_DEPENDENCY_REQUIRED
    )
    assert readiness.findings[-1].transaction_ids == ("TARGET-B",)


def test_manifest_requires_cash_to_depend_on_a_position_child() -> None:
    children = _children()
    unbound_cash = replace(children[3], dependency_transaction_ids=())
    candidate = (*children[:3], unbound_cash)

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=candidate),
        observed_children=candidate,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert readiness.findings[-1].reason == (
        CorporateActionManifestReason.NON_POSITION_DEPENDENCY_REQUIRED
    )
    assert readiness.findings[-1].transaction_ids == ("CASH",)


def test_manifest_rejects_target_that_reuses_source_instrument() -> None:
    children = _children()
    invalid_target = replace(children[1], target_instrument_id="PARENT-SEC")
    candidate = (children[0], invalid_target, *children[2:])

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=candidate),
        observed_children=candidate,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert CorporateActionManifestReason.TARGET_INSTRUMENT_EQUALS_SOURCE in {
        finding.reason for finding in readiness.findings
    }


def test_manifest_returns_ready_only_for_exact_complete_observation() -> None:
    children = _children()

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=children),
        observed_children=tuple(reversed(children)),
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.READY
    assert readiness.ordered_children == children
    assert readiness.findings == ()
    assert readiness.manifest_content_hash is not None
    assert len(readiness.manifest_content_hash) == 64


@pytest.mark.parametrize(
    ("observed", "reason", "status"),
    [
        (
            _children()[:-1],
            CorporateActionManifestReason.MISSING_EXPECTED_CHILD,
            CorporateActionManifestReadinessStatus.AWAITING_CHILDREN,
        ),
        (
            (
                *_children(),
                _child("EXTRA", "FEE", "CHARGE", dependencies=("CASH",)),
            ),
            CorporateActionManifestReason.UNEXPECTED_CHILD,
            CorporateActionManifestReadinessStatus.INVALID,
        ),
        (
            (
                _children()[0],
                replace(_children()[1], target_instrument_id="WRONG-SEC"),
                *_children()[2:],
            ),
            CorporateActionManifestReason.OBSERVED_CHILD_MISMATCH,
            CorporateActionManifestReadinessStatus.INVALID,
        ),
    ],
)
def test_manifest_parks_incomplete_or_conflicting_observations(
    observed: tuple[CorporateActionEventChild, ...],
    reason: CorporateActionManifestReason,
    status: CorporateActionManifestReadinessStatus,
) -> None:
    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(),
        observed_children=observed,
    )

    assert readiness.status == status
    assert reason in {finding.reason for finding in readiness.findings}


def test_manifest_content_hash_is_independent_of_expected_child_order() -> None:
    children = _children()

    assert (
        _manifest(children=children).content_hash
        == _manifest(children=tuple(reversed(children))).content_hash
    )


def test_manifest_and_child_expose_the_exact_canonical_persistence_payload() -> None:
    manifest = _manifest()
    payload = manifest.lineage_payload()

    assert payload["canonical_payload_version"] == 1
    first_child = manifest.expected_children[0]

    assert payload["portfolio_id"] == manifest.portfolio_id
    assert payload["source_reference"] == manifest.source_reference.lineage_payload()
    persisted_children = payload["expected_children"]
    assert isinstance(persisted_children, list)
    assert first_child.lineage_payload() in persisted_children
    assert first_child.lineage_payload()["canonical_payload_version"] == 1
    assert len(first_child.content_hash) == 64


def test_manifest_identity_and_observation_ignore_dependency_declaration_order() -> None:
    children = _children()
    reordered_cash = replace(
        children[3],
        dependency_transaction_ids=tuple(reversed(children[3].dependency_transaction_ids)),
    )
    reordered = (*children[:3], reordered_cash)

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=children),
        observed_children=reordered,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.READY
    assert _manifest(children=children).content_hash == _manifest(children=reordered).content_hash


@pytest.mark.parametrize("include_cash", [False, True])
def test_manifest_requires_target_cohort_before_readiness(include_cash: bool) -> None:
    source = _children()[0]
    children = (
        source,
        *(
            (
                _child(
                    "CASH",
                    "CASH_CONSIDERATION",
                    "CASH_CONSIDERATION",
                    dependencies=("SOURCE",),
                ),
            )
            if include_cash
            else ()
        ),
    )

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=children),
        observed_children=children,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert CorporateActionManifestReason.TARGET_CHILD_REQUIRED in {
        finding.reason for finding in readiness.findings
    }


@pytest.mark.parametrize("observed", [(_children()[1],), (_children()[3],)])
def test_manifest_parks_valid_out_of_order_arrivals(
    observed: tuple[CorporateActionEventChild, ...],
) -> None:
    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(),
        observed_children=observed,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.AWAITING_CHILDREN
    assert {finding.reason for finding in readiness.findings} == {
        CorporateActionManifestReason.MISSING_EXPECTED_CHILD
    }


def test_manifest_rejects_malformed_later_target_actual_instrument() -> None:
    children = _children()
    malformed = replace(children[2], instrument_id="WRONG-SEC")
    candidate = (*children[:2], malformed, children[3])

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=candidate),
        observed_children=candidate,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert CorporateActionManifestReason.TARGET_CHILD_INSTRUMENT_MISMATCH in {
        finding.reason for finding in readiness.findings
    }


def test_manifest_requires_cash_dependency_on_every_target() -> None:
    children = _children()
    incomplete_cash = replace(children[3], dependency_transaction_ids=("TARGET-A",))
    candidate = (*children[:3], incomplete_cash)

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=candidate),
        observed_children=candidate,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert readiness.findings[-1].reason == (
        CorporateActionManifestReason.NON_POSITION_DEPENDENCY_REQUIRED
    )


def test_manifest_preserves_structural_finding_identity() -> None:
    children = _children()
    cycle = (
        replace(children[0], dependency_transaction_ids=("TARGET-A",)),
        *children[1:],
    )

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=cycle),
        observed_children=cycle,
    )

    graph_findings = readiness.findings[0].graph_findings
    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    cycle_finding = next(
        finding
        for finding in graph_findings
        if finding.reason == CorporateActionEventGraphReason.DEPENDENCY_CYCLE
    )
    assert cycle_finding.transaction_ids == ("SOURCE", "TARGET-A")


def test_manifest_rejects_duplicate_observation_with_exact_identity() -> None:
    children = _children()

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(),
        observed_children=(*children, children[1]),
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    finding = readiness.findings[0]
    assert finding.transaction_ids == ("TARGET-A",)
    assert finding.graph_findings[0].transaction_ids == ("TARGET-A",)


@pytest.mark.parametrize("event_type", ["MERGER", "UNKNOWN_EVENT"])
def test_manifest_enforces_declared_event_type_policy(event_type: str) -> None:
    manifest = replace(_manifest(), corporate_action_type=event_type)

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=manifest,
        observed_children=_children(),
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert readiness.findings


@pytest.mark.parametrize(
    ("event_type", "source_type", "source_role", "target_type"),
    [
        ("SPIN_OFF", "SPIN_OFF", "SOURCE_POSITION_REDUCE", "SPIN_IN"),
        ("DEMERGER", "DEMERGER_OUT", "SOURCE_POSITION_REDUCE", "DEMERGER_IN"),
        ("MERGER", "MERGER_OUT", "SOURCE_POSITION_CLOSE", "MERGER_IN"),
        (
            "MANDATORY_EXCHANGE",
            "EXCHANGE_OUT",
            "SOURCE_POSITION_CLOSE",
            "EXCHANGE_IN",
        ),
        (
            "SECURITY_REPLACEMENT",
            "REPLACEMENT_OUT",
            "SOURCE_POSITION_CLOSE",
            "REPLACEMENT_IN",
        ),
    ],
)
def test_manifest_accepts_each_governed_parent_cohort(
    event_type: str,
    source_type: str,
    source_role: str,
    target_type: str,
) -> None:
    source = _child(
        "SOURCE",
        source_type,
        source_role,
        instrument="SOURCE-SEC",
        source="SOURCE-SEC",
    )
    target = _child(
        "TARGET",
        target_type,
        "TARGET_POSITION_ADD",
        dependencies=("SOURCE",),
        instrument="TARGET-SEC",
        source="SOURCE-SEC",
        target="TARGET-SEC",
    )
    children = (source, target)
    manifest = replace(
        _manifest(children=children),
        corporate_action_type=event_type,
    )

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=manifest,
        observed_children=tuple(reversed(children)),
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.READY
    assert readiness.ordered_children == children


@pytest.mark.parametrize(
    ("child_index", "changes", "reason"),
    [
        (
            0,
            {"instrument_id": "WRONG-SOURCE"},
            CorporateActionManifestReason.SOURCE_CHILD_INSTRUMENT_MISMATCH,
        ),
        (
            1,
            {"source_instrument_id": "WRONG-SOURCE"},
            CorporateActionManifestReason.TARGET_SOURCE_INSTRUMENT_MISMATCH,
        ),
    ],
)
def test_manifest_binds_declared_instruments_to_actual_children(
    child_index: int,
    changes: dict[str, str],
    reason: CorporateActionManifestReason,
) -> None:
    children = list(_children())
    children[child_index] = replace(children[child_index], **changes)
    candidate = tuple(children)

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=candidate),
        observed_children=candidate,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert reason in {finding.reason for finding in readiness.findings}


def test_manifest_requires_cash_in_lieu_to_reference_its_target_instrument() -> None:
    source, target = _children()[:2]
    cash_in_lieu = _child(
        "CIL",
        "CASH_IN_LIEU",
        "CASH_IN_LIEU",
        dependencies=("TARGET-A",),
        instrument="TARGET-SEC-A",
    )
    valid = (source, target, cash_in_lieu)
    invalid = (*valid[:2], replace(cash_in_lieu, instrument_id="WRONG-SEC"))

    assert (
        evaluate_corporate_action_manifest_readiness(
            manifest=_manifest(children=valid),
            observed_children=valid,
        ).status
        == CorporateActionManifestReadinessStatus.READY
    )
    invalid_readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=invalid),
        observed_children=invalid,
    )
    assert invalid_readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert invalid_readiness.findings[-1].reason == (
        CorporateActionManifestReason.NON_POSITION_DEPENDENCY_REQUIRED
    )


def test_manifest_governs_settlement_charge_and_tax_prerequisites() -> None:
    source, target = _children()[:2]
    cash = _child(
        "CASH",
        "CASH_CONSIDERATION",
        "CASH_CONSIDERATION",
        dependencies=("TARGET-A",),
    )
    settlement = _child(
        "SETTLEMENT",
        "ADJUSTMENT",
        "CASH_SETTLEMENT",
        dependencies=("CASH",),
    )
    fee = _child(
        "FEE",
        "FEE",
        "CHARGE",
        dependencies=("TARGET-A", "CASH"),
    )
    tax = _child(
        "TAX",
        "TAX",
        "TAX",
        dependencies=("TARGET-A", "CASH"),
    )
    valid = (source, target, cash, settlement, fee, tax)

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=valid),
        observed_children=valid,
    )
    invalid_fee = replace(fee, dependency_transaction_ids=("TARGET-A",))
    invalid = (source, target, cash, settlement, invalid_fee, tax)
    invalid_readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=invalid),
        observed_children=invalid,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.READY
    assert invalid_readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert invalid_readiness.findings[-1].transaction_ids == ("FEE",)


def test_manifest_conflicting_observation_preserves_child_identity() -> None:
    expected = _children()
    conflicting = replace(expected[1], target_instrument_id="CONFLICT")

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(),
        observed_children=(*expected, conflicting),
    )

    finding = readiness.findings[0]
    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert finding.transaction_ids == ("TARGET-A",)
    assert finding.graph_findings[0].reason == (
        CorporateActionEventGraphReason.CONFLICTING_CHILD_DEFINITION
    )


def test_manifest_hash_binds_actual_child_instrument() -> None:
    children = _children()
    changed = (
        children[0],
        replace(children[1], instrument_id="DIFFERENT-ACTUAL-INSTRUMENT"),
        *children[2:],
    )

    assert _manifest(children=children).content_hash != _manifest(children=changed).content_hash


def test_manifest_hash_binds_portfolio_ownership() -> None:
    manifest = _manifest()

    assert (
        manifest.content_hash != replace(manifest, portfolio_id="PB-CH-ADVISORY-002").content_hash
    )
