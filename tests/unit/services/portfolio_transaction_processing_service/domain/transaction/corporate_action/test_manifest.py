"""Test source-owned corporate-action parent-manifest readiness."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from portfolio_common.domain.calculation_lineage import FinancialSourceReference

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)

CorporateActionEventChild = corporate_action.CorporateActionEventChild
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
        source_instrument_id=source,
        target_instrument_id=target,
    )


def _children() -> tuple[CorporateActionEventChild, ...]:
    return (
        _child(
            "SOURCE",
            "DEMERGER_OUT",
            "SOURCE_POSITION_REDUCE",
            source="PARENT-SEC",
        ),
        _child(
            "TARGET-A",
            "DEMERGER_IN",
            "TARGET_POSITION_ADD",
            dependencies=("SOURCE",),
            source="PARENT-SEC",
            target="TARGET-SEC-A",
            sequence=1,
        ),
        _child(
            "TARGET-B",
            "DEMERGER_IN",
            "TARGET_POSITION_ADD",
            dependencies=("SOURCE",),
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
        source="PARENT-SEC",
        target="TARGET-SEC",
    )

    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(children=(target,)),
        observed_children=(target,),
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.INVALID
    assert readiness.findings[0].reason == (
        CorporateActionManifestReason.TARGET_SOURCE_DEPENDENCY_REQUIRED
    )


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
    assert readiness.findings[-1].reason == (
        CorporateActionManifestReason.TARGET_INSTRUMENT_EQUALS_SOURCE
    )


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
    ("observed", "reason"),
    [
        (_children()[:-1], CorporateActionManifestReason.MISSING_EXPECTED_CHILD),
        (
            (
                *_children(),
                _child("EXTRA", "FEE", "CHARGE", dependencies=("CASH",)),
            ),
            CorporateActionManifestReason.UNEXPECTED_CHILD,
        ),
        (
            (
                _children()[0],
                replace(_children()[1], target_instrument_id="WRONG-SEC"),
                *_children()[2:],
            ),
            CorporateActionManifestReason.OBSERVED_CHILD_MISMATCH,
        ),
    ],
)
def test_manifest_parks_incomplete_or_conflicting_observations(
    observed: tuple[CorporateActionEventChild, ...],
    reason: CorporateActionManifestReason,
) -> None:
    readiness = evaluate_corporate_action_manifest_readiness(
        manifest=_manifest(),
        observed_children=observed,
    )

    assert readiness.status == CorporateActionManifestReadinessStatus.AWAITING_CHILDREN
    assert reason in {finding.reason for finding in readiness.findings}


def test_manifest_content_hash_is_independent_of_expected_child_order() -> None:
    children = _children()

    assert (
        _manifest(children=children).content_hash
        == _manifest(children=tuple(reversed(children))).content_hash
    )


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
