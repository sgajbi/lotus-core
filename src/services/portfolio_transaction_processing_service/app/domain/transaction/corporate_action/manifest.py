"""Evaluate source-owned corporate-action manifests before execution is permitted."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    canonical_content_hash,
)

from .classification import QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS
from .cohort_policy import CorporateActionCohortPolicy, corporate_action_cohort_policy
from .event_graph import (
    CorporateActionEventChild,
    CorporateActionEventGraph,
    CorporateActionEventGraphFinding,
    CorporateActionEventGraphReason,
    CorporateActionEventStructuralStatus,
    resolve_corporate_action_event_graph,
)


class CorporateActionManifestReadinessStatus(StrEnum):
    """Classify authoritative parent-manifest readiness."""

    AWAITING_MANIFEST = "AWAITING_MANIFEST"
    AWAITING_COMPLETION = "AWAITING_COMPLETION"
    AWAITING_CHILDREN = "AWAITING_CHILDREN"
    INVALID = "INVALID"
    READY = "READY"


class CorporateActionManifestReason(StrEnum):
    """Expose stable parent-manifest and observation defects."""

    MANIFEST_REQUIRED = "CA_MANIFEST_REQUIRED"
    COMPLETION_NOT_DECLARED = "CA_MANIFEST_COMPLETION_NOT_DECLARED"
    INVALID_GRAPH = "CA_MANIFEST_INVALID_GRAPH"
    INVALID_ROLE_FOR_TRANSACTION_TYPE = "CA_MANIFEST_INVALID_ROLE_FOR_TRANSACTION_TYPE"
    UNSUPPORTED_CORPORATE_ACTION_TYPE = "CA_MANIFEST_UNSUPPORTED_CORPORATE_ACTION_TYPE"
    CHILD_TYPE_NOT_ALLOWED = "CA_MANIFEST_CHILD_TYPE_NOT_ALLOWED"
    SOURCE_CHILD_REQUIRED = "CA_MANIFEST_SOURCE_CHILD_REQUIRED"
    SOURCE_CHILD_CARDINALITY = "CA_MANIFEST_SOURCE_CHILD_CARDINALITY"
    TARGET_CHILD_REQUIRED = "CA_MANIFEST_TARGET_CHILD_REQUIRED"
    SOURCE_INSTRUMENT_REQUIRED = "CA_MANIFEST_SOURCE_INSTRUMENT_REQUIRED"
    SOURCE_CHILD_INSTRUMENT_MISMATCH = "CA_MANIFEST_SOURCE_CHILD_INSTRUMENT_MISMATCH"
    TARGET_INSTRUMENT_REQUIRED = "CA_MANIFEST_TARGET_INSTRUMENT_REQUIRED"
    TARGET_CHILD_INSTRUMENT_MISMATCH = "CA_MANIFEST_TARGET_CHILD_INSTRUMENT_MISMATCH"
    TARGET_INSTRUMENT_EQUALS_SOURCE = "CA_MANIFEST_TARGET_INSTRUMENT_EQUALS_SOURCE"
    TARGET_SOURCE_DEPENDENCY_REQUIRED = "CA_MANIFEST_TARGET_SOURCE_DEPENDENCY_REQUIRED"
    TARGET_SOURCE_INSTRUMENT_MISMATCH = "CA_MANIFEST_TARGET_SOURCE_INSTRUMENT_MISMATCH"
    NON_POSITION_DEPENDENCY_REQUIRED = "CA_MANIFEST_NON_POSITION_DEPENDENCY_REQUIRED"
    MISSING_EXPECTED_CHILD = "CA_MANIFEST_MISSING_EXPECTED_CHILD"
    UNEXPECTED_CHILD = "CA_MANIFEST_UNEXPECTED_CHILD"
    OBSERVED_CHILD_MISMATCH = "CA_MANIFEST_OBSERVED_CHILD_MISMATCH"


@dataclass(frozen=True, slots=True)
class CorporateActionParentManifest:
    """Declare the authoritative expected child set for one parent event version."""

    corporate_action_event_id: str
    tenant_id: str
    legal_book_id: str
    portfolio_id: str
    linked_transaction_group_id: str
    parent_event_reference: str
    corporate_action_type: str
    version: int
    completion_declared: bool
    expected_children: tuple[CorporateActionEventChild, ...]
    source_reference: FinancialSourceReference

    def __post_init__(self) -> None:
        for field_name in (
            "corporate_action_event_id",
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            "linked_transaction_group_id",
            "parent_event_reference",
            "corporate_action_type",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())
        object.__setattr__(self, "corporate_action_type", self.corporate_action_type.upper())
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.completion_declared, bool):
            raise ValueError("completion_declared must be a boolean")
        if not isinstance(self.expected_children, tuple) or not all(
            isinstance(child, CorporateActionEventChild) for child in self.expected_children
        ):
            raise ValueError(
                "expected_children must be a tuple of CorporateActionEventChild values"
            )
        if not isinstance(self.source_reference, FinancialSourceReference):
            raise ValueError("source_reference must be a FinancialSourceReference")

    @property
    def content_hash(self) -> str:
        """Bind parent identity, expected nodes/edges and source-version evidence."""

        return cast(str, canonical_content_hash(self.lineage_payload()))

    def lineage_payload(self) -> dict[str, object]:
        """Return the closed canonical parent-manifest representation."""

        return {
            "canonical_payload_version": 1,
            "completion_declared": self.completion_declared,
            "corporate_action_event_id": self.corporate_action_event_id,
            "corporate_action_type": self.corporate_action_type,
            "expected_children": [
                child.lineage_payload()
                for child in sorted(
                    self.expected_children,
                    key=lambda value: value.transaction_id,
                )
            ],
            "legal_book_id": self.legal_book_id,
            "linked_transaction_group_id": self.linked_transaction_group_id,
            "parent_event_reference": self.parent_event_reference,
            "portfolio_id": self.portfolio_id,
            "source_reference": self.source_reference.lineage_payload(),
            "tenant_id": self.tenant_id,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class CorporateActionManifestFinding:
    """Describe one deterministic readiness defect."""

    reason: CorporateActionManifestReason
    transaction_ids: tuple[str, ...] = ()
    graph_findings: tuple[CorporateActionEventGraphFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class CorporateActionManifestReadiness:
    """Return manifest readiness and the only permitted execution order."""

    status: CorporateActionManifestReadinessStatus
    ordered_children: tuple[CorporateActionEventChild, ...]
    findings: tuple[CorporateActionManifestFinding, ...]
    manifest_content_hash: str | None


def evaluate_corporate_action_manifest_readiness(
    *,
    manifest: CorporateActionParentManifest | None,
    observed_children: tuple[CorporateActionEventChild, ...],
) -> CorporateActionManifestReadiness:
    """Fail closed until an authoritative, complete and exactly observed manifest is ready."""

    if manifest is None:
        return _readiness(
            CorporateActionManifestReadinessStatus.AWAITING_MANIFEST,
            (CorporateActionManifestFinding(CorporateActionManifestReason.MANIFEST_REQUIRED),),
        )
    if not manifest.completion_declared:
        return _readiness(
            CorporateActionManifestReadinessStatus.AWAITING_COMPLETION,
            (
                CorporateActionManifestFinding(
                    CorporateActionManifestReason.COMPLETION_NOT_DECLARED
                ),
            ),
            manifest=manifest,
        )

    graph = CorporateActionEventGraph(
        corporate_action_event_id=manifest.corporate_action_event_id,
        linked_transaction_group_id=manifest.linked_transaction_group_id,
        parent_event_reference=manifest.parent_event_reference,
        version=manifest.version,
        children=manifest.expected_children,
    )
    structural_plan = resolve_corporate_action_event_graph(graph)
    findings: list[CorporateActionManifestFinding] = []
    if structural_plan.status != CorporateActionEventStructuralStatus.STRUCTURALLY_VALID:
        findings.append(
            CorporateActionManifestFinding(
                CorporateActionManifestReason.INVALID_GRAPH,
                graph_findings=structural_plan.findings,
            )
        )
    findings.extend(_semantic_findings(manifest))
    if findings:
        return _readiness(
            CorporateActionManifestReadinessStatus.INVALID,
            findings,
            manifest=manifest,
        )

    observed_identity_findings = _observed_identity_findings(observed_children)
    if observed_identity_findings:
        return _readiness(
            CorporateActionManifestReadinessStatus.INVALID,
            observed_identity_findings,
            manifest=manifest,
        )

    expected_by_id = {child.transaction_id: child for child in manifest.expected_children}
    observed_by_id = {child.transaction_id: child for child in observed_children}
    missing = tuple(sorted(expected_by_id.keys() - observed_by_id.keys()))
    unexpected = tuple(sorted(observed_by_id.keys() - expected_by_id.keys()))
    mismatched = tuple(
        sorted(
            transaction_id
            for transaction_id in expected_by_id.keys() & observed_by_id.keys()
            if _child_payload(expected_by_id[transaction_id])
            != _child_payload(observed_by_id[transaction_id])
        )
    )
    if unexpected:
        findings.append(
            CorporateActionManifestFinding(
                CorporateActionManifestReason.UNEXPECTED_CHILD,
                transaction_ids=unexpected,
            )
        )
    if mismatched:
        findings.append(
            CorporateActionManifestFinding(
                CorporateActionManifestReason.OBSERVED_CHILD_MISMATCH,
                transaction_ids=mismatched,
            )
        )
    if unexpected or mismatched:
        return _readiness(
            CorporateActionManifestReadinessStatus.INVALID,
            findings,
            manifest=manifest,
        )
    if missing:
        findings.append(
            CorporateActionManifestFinding(
                CorporateActionManifestReason.MISSING_EXPECTED_CHILD,
                transaction_ids=missing,
            )
        )
        return _readiness(
            CorporateActionManifestReadinessStatus.AWAITING_CHILDREN,
            findings,
            manifest=manifest,
        )
    return CorporateActionManifestReadiness(
        status=CorporateActionManifestReadinessStatus.READY,
        ordered_children=structural_plan.ordered_children,
        findings=(),
        manifest_content_hash=manifest.content_hash,
    )


_SOURCE_ROLE_BY_TYPE = {
    "SPIN_OFF": frozenset({"SOURCE_POSITION_REDUCE"}),
    "DEMERGER_OUT": frozenset({"SOURCE_POSITION_REDUCE"}),
    **{
        transaction_type: frozenset({"SOURCE_POSITION_CLOSE", "SOURCE_POSITION_REDUCE"})
        for transaction_type in QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS
    },
}
_TARGET_SOURCE_TYPE = {
    "SPIN_IN": "SPIN_OFF",
    "DEMERGER_IN": "DEMERGER_OUT",
    **{target: source for source, target in QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS.items()},
}
_ROLE_BY_NON_POSITION_TYPE = {
    "CASH_CONSIDERATION": "CASH_CONSIDERATION",
    "CASH_IN_LIEU": "CASH_IN_LIEU",
    "ADJUSTMENT": "CASH_SETTLEMENT",
    "FEE": "CHARGE",
    "TAX": "TAX",
}


def _semantic_findings(
    manifest: CorporateActionParentManifest,
) -> tuple[CorporateActionManifestFinding, ...]:
    children = manifest.expected_children
    policy = corporate_action_cohort_policy(manifest.corporate_action_type)
    if policy is None:
        return (
            CorporateActionManifestFinding(
                CorporateActionManifestReason.UNSUPPORTED_CORPORATE_ACTION_TYPE
            ),
        )

    findings, target_children = _cohort_shape_findings(children, policy)
    children_by_id = {child.transaction_id: child for child in children}
    target_ids = frozenset(child.transaction_id for child in target_children)
    consideration_ids = frozenset(
        child.transaction_id
        for child in children
        if child.transaction_type in {"CASH_CONSIDERATION", "CASH_IN_LIEU"}
    )
    for child in sorted(children, key=lambda value: value.transaction_id):
        findings.extend(
            _child_semantic_findings(
                child,
                policy=policy,
                children_by_id=children_by_id,
                target_children=target_children,
                target_ids=target_ids,
                consideration_ids=consideration_ids,
            )
        )
    return tuple(findings)


def _cohort_shape_findings(
    children: tuple[CorporateActionEventChild, ...],
    policy: CorporateActionCohortPolicy,
) -> tuple[list[CorporateActionManifestFinding], tuple[CorporateActionEventChild, ...]]:
    findings: list[CorporateActionManifestFinding] = []
    disallowed_children = tuple(
        sorted(
            child.transaction_id
            for child in children
            if child.transaction_type not in policy.allowed_transaction_types
        )
    )
    if disallowed_children:
        findings.append(
            CorporateActionManifestFinding(
                CorporateActionManifestReason.CHILD_TYPE_NOT_ALLOWED,
                transaction_ids=disallowed_children,
            )
        )
    source_children = tuple(
        child for child in children if child.transaction_type == policy.source_transaction_type
    )
    target_children = tuple(
        child for child in children if child.transaction_type == policy.target_transaction_type
    )
    if not source_children:
        findings.append(
            CorporateActionManifestFinding(CorporateActionManifestReason.SOURCE_CHILD_REQUIRED)
        )
    elif len(source_children) != 1:
        findings.append(
            CorporateActionManifestFinding(
                CorporateActionManifestReason.SOURCE_CHILD_CARDINALITY,
                transaction_ids=tuple(sorted(child.transaction_id for child in source_children)),
            )
        )
    if not target_children:
        findings.append(
            CorporateActionManifestFinding(CorporateActionManifestReason.TARGET_CHILD_REQUIRED)
        )
    return findings, target_children


def _child_semantic_findings(
    child: CorporateActionEventChild,
    *,
    policy: CorporateActionCohortPolicy,
    children_by_id: dict[str, CorporateActionEventChild],
    target_children: tuple[CorporateActionEventChild, ...],
    target_ids: frozenset[str],
    consideration_ids: frozenset[str],
) -> tuple[CorporateActionManifestFinding, ...]:
    if child.transaction_type in _SOURCE_ROLE_BY_TYPE:
        return _source_child_findings(child, policy)
    expected_source_type = _TARGET_SOURCE_TYPE.get(child.transaction_type)
    if expected_source_type is not None:
        return _target_child_findings(child, expected_source_type, children_by_id)
    return _non_position_child_findings(
        child,
        target_children=target_children,
        target_ids=target_ids,
        consideration_ids=consideration_ids,
    )


def _source_child_findings(
    child: CorporateActionEventChild,
    policy: CorporateActionCohortPolicy,
) -> tuple[CorporateActionManifestFinding, ...]:
    findings: list[CorporateActionManifestFinding] = []
    if child.child_role != policy.source_role:
        findings.append(
            _finding(CorporateActionManifestReason.INVALID_ROLE_FOR_TRANSACTION_TYPE, child)
        )
    if child.source_instrument_id is None:
        findings.append(_finding(CorporateActionManifestReason.SOURCE_INSTRUMENT_REQUIRED, child))
    if child.instrument_id is None:
        findings.append(_finding(CorporateActionManifestReason.SOURCE_INSTRUMENT_REQUIRED, child))
    elif (
        child.source_instrument_id is not None and child.instrument_id != child.source_instrument_id
    ):
        findings.append(
            _finding(CorporateActionManifestReason.SOURCE_CHILD_INSTRUMENT_MISMATCH, child)
        )
    return tuple(findings)


def _target_child_findings(
    child: CorporateActionEventChild,
    expected_source_type: str,
    children_by_id: dict[str, CorporateActionEventChild],
) -> tuple[CorporateActionManifestFinding, ...]:
    findings: list[CorporateActionManifestFinding] = []
    if child.child_role != "TARGET_POSITION_ADD":
        findings.append(
            _finding(CorporateActionManifestReason.INVALID_ROLE_FOR_TRANSACTION_TYPE, child)
        )
    if child.source_instrument_id is None:
        findings.append(_finding(CorporateActionManifestReason.SOURCE_INSTRUMENT_REQUIRED, child))
    if child.target_instrument_id is None:
        findings.append(_finding(CorporateActionManifestReason.TARGET_INSTRUMENT_REQUIRED, child))
    elif child.target_instrument_id == child.source_instrument_id:
        findings.append(
            _finding(CorporateActionManifestReason.TARGET_INSTRUMENT_EQUALS_SOURCE, child)
        )
    if child.instrument_id is None:
        findings.append(_finding(CorporateActionManifestReason.TARGET_INSTRUMENT_REQUIRED, child))
    elif (
        child.target_instrument_id is not None and child.instrument_id != child.target_instrument_id
    ):
        findings.append(
            _finding(CorporateActionManifestReason.TARGET_CHILD_INSTRUMENT_MISMATCH, child)
        )

    compatible_sources = tuple(
        children_by_id[dependency_id]
        for dependency_id in child.dependency_transaction_ids
        if dependency_id in children_by_id
        and children_by_id[dependency_id].transaction_type == expected_source_type
    )
    if len(compatible_sources) != 1:
        findings.append(
            _finding(CorporateActionManifestReason.TARGET_SOURCE_DEPENDENCY_REQUIRED, child)
        )
    elif child.source_instrument_id != compatible_sources[0].instrument_id:
        findings.append(
            _finding(CorporateActionManifestReason.TARGET_SOURCE_INSTRUMENT_MISMATCH, child)
        )
    return tuple(findings)


def _non_position_child_findings(
    child: CorporateActionEventChild,
    *,
    target_children: tuple[CorporateActionEventChild, ...],
    target_ids: frozenset[str],
    consideration_ids: frozenset[str],
) -> tuple[CorporateActionManifestFinding, ...]:
    expected_role = _ROLE_BY_NON_POSITION_TYPE.get(child.transaction_type)
    if expected_role is None or child.child_role != expected_role:
        return (_finding(CorporateActionManifestReason.INVALID_ROLE_FOR_TRANSACTION_TYPE, child),)
    if _has_governed_non_position_dependencies(
        child,
        target_children=target_children,
        target_ids=target_ids,
        consideration_ids=consideration_ids,
    ):
        return ()
    return (_finding(CorporateActionManifestReason.NON_POSITION_DEPENDENCY_REQUIRED, child),)


def _has_governed_non_position_dependencies(
    child: CorporateActionEventChild,
    *,
    target_children: tuple[CorporateActionEventChild, ...],
    target_ids: frozenset[str],
    consideration_ids: frozenset[str],
) -> bool:
    dependencies = frozenset(child.dependency_transaction_ids)
    if child.transaction_type == "CASH_CONSIDERATION":
        return target_ids.issubset(dependencies)
    if child.transaction_type == "CASH_IN_LIEU":
        matching_target_ids = frozenset(
            target.transaction_id
            for target in target_children
            if target.instrument_id == child.instrument_id
        )
        return bool(matching_target_ids.intersection(dependencies))
    if child.transaction_type == "ADJUSTMENT":
        return len(dependencies) == 1 and dependencies.issubset(consideration_ids)
    terminal_ids = target_ids.union(consideration_ids)
    return bool(terminal_ids) and terminal_ids.issubset(dependencies)


def _child_payload(child: CorporateActionEventChild) -> dict[str, object]:
    return cast(dict[str, object], child.lineage_payload())


def _observed_identity_findings(
    children: tuple[CorporateActionEventChild, ...],
) -> tuple[CorporateActionManifestFinding, ...]:
    """Reject duplicate/conflicting observations without requiring every dependency to arrive."""

    first_by_id: dict[str, CorporateActionEventChild] = {}
    graph_findings: list[CorporateActionEventGraphFinding] = []
    for child in children:
        existing = first_by_id.get(child.transaction_id)
        if existing is None:
            first_by_id[child.transaction_id] = child
            continue
        graph_findings.append(
            CorporateActionEventGraphFinding(
                reason=(
                    CorporateActionEventGraphReason.DUPLICATE_CHILD_ID
                    if _child_payload(existing) == _child_payload(child)
                    else CorporateActionEventGraphReason.CONFLICTING_CHILD_DEFINITION
                ),
                transaction_ids=(child.transaction_id,),
            )
        )
    if not graph_findings:
        return ()
    canonical_findings = tuple(
        sorted(
            graph_findings,
            key=lambda finding: (
                finding.reason,
                finding.transaction_ids,
                finding.dependency_transaction_ids,
            ),
        )
    )
    return (
        CorporateActionManifestFinding(
            CorporateActionManifestReason.INVALID_GRAPH,
            transaction_ids=tuple(
                sorted(
                    transaction_id
                    for finding in canonical_findings
                    for transaction_id in finding.transaction_ids
                )
            ),
            graph_findings=canonical_findings,
        ),
    )


def _finding(
    reason: CorporateActionManifestReason,
    child: CorporateActionEventChild,
) -> CorporateActionManifestFinding:
    return CorporateActionManifestFinding(reason, transaction_ids=(child.transaction_id,))


def _readiness(
    status: CorporateActionManifestReadinessStatus,
    findings: tuple[CorporateActionManifestFinding, ...] | list[CorporateActionManifestFinding],
    *,
    manifest: CorporateActionParentManifest | None = None,
) -> CorporateActionManifestReadiness:
    return CorporateActionManifestReadiness(
        status=status,
        ordered_children=(),
        findings=tuple(findings),
        manifest_content_hash=manifest.content_hash if manifest is not None else None,
    )
