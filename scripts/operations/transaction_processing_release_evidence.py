"""Pure evidence policy for controlled transaction-runtime release rehearsals."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence, cast

from scripts.operations.transaction_processing_cutover_offsets import ConsumerGroupSnapshot
from scripts.release.render_release_deployment import (
    DEPLOYMENT_TARGETS,
    DeploymentRenderError,
    release_image_ref,
)

RECEIPT_SCHEMA = "lotus-core.transaction-processing-release-rehearsal.v1"
EVIDENCE_CLASSIFICATION = "local_compose_release_rehearsal"
SERVICE_NAME = "portfolio_transaction_processing_service"
COMPOSE_PROJECT_PREFIX = "lotus-integration-transaction-release-rehearsal-"
SHARED_COMPOSE_PROJECTS = frozenset({"lotus-core-app-local", "lotus-core-canonical-ui"})
UNKNOWN_METADATA_VALUE = "unknown"

_SECRET_KEY_MARKERS = (
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)
_URI_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s]+@", re.IGNORECASE)


class ReleaseEvidenceError(ValueError):
    """Raised when release rehearsal evidence cannot support a truthful receipt."""


class RehearsalPhase(StrEnum):
    """Ordered phases required for one controlled local release rehearsal."""

    PREFLIGHT = "preflight"
    BASELINE = "baseline"
    OFFSET_HANDOFF = "offset_handoff"
    CANDIDATE_DEPLOY = "candidate_deploy"
    CANARY = "canary"
    ROLLBACK = "rollback"
    CLEANUP = "cleanup"


REQUIRED_PHASE_ORDER = tuple(RehearsalPhase)


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    """Supply-chain and runtime identity authorized by one release manifest."""

    service: str
    git_commit_sha: str
    digest_image_ref: str
    image_digest: str
    runtime_env: Mapping[str, str]
    oci_labels: Mapping[str, str]
    sbom_generated: bool
    vulnerability_scan_status: str
    image_signed: bool
    provenance_attestation_generated: bool


@dataclass(frozen=True, slots=True)
class PhaseResult:
    """One bounded rehearsal phase and its redacted evidence."""

    phase: RehearsalPhase
    status: str
    started_at: str
    ended_at: str
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.status not in {"passed", "failed"}:
            raise ReleaseEvidenceError(f"unsupported phase status: {self.status}")
        if not self.started_at or not self.ended_at:
            raise ReleaseEvidenceError(f"phase timestamps are required: {self.phase}")


@dataclass(frozen=True, slots=True)
class FinancialEffectEvidence:
    """Fail-closed canary or rollback reconciliation result."""

    expected_transactions: int
    persisted_transactions: int
    expected_positions: int
    persisted_positions: int
    pending_outbox: int
    failed_outbox: int
    dlq_count: int
    duplicate_financial_effects: int
    reconciliation_findings: int
    unresolved_work: int

    def findings(self) -> tuple[str, ...]:
        findings: list[str] = []
        if self.expected_transactions < 1:
            findings.append("expected transaction count must be positive")
        if self.persisted_transactions != self.expected_transactions:
            findings.append("persisted transaction count does not reconcile")
        if self.expected_positions < 1:
            findings.append("expected position count must be positive")
        if self.persisted_positions != self.expected_positions:
            findings.append("persisted position count does not reconcile")
        for field_name in (
            "pending_outbox",
            "failed_outbox",
            "dlq_count",
            "duplicate_financial_effects",
            "reconciliation_findings",
            "unresolved_work",
        ):
            if getattr(self, field_name) != 0:
                findings.append(f"{field_name} must be zero")
        return tuple(findings)


def release_identity(manifest: Mapping[str, Any]) -> ReleaseIdentity:
    """Validate one immutable release manifest and retain its governed identity."""

    target = DEPLOYMENT_TARGETS[SERVICE_NAME]
    try:
        digest_image_ref = release_image_ref(dict(manifest), target=target)
    except DeploymentRenderError as exc:
        raise ReleaseEvidenceError(str(exc)) from exc
    runtime_env = _string_mapping(manifest.get("runtime_env"), field_name="runtime_env")
    git_commit_sha = _required_string(manifest, "git_commit_sha")
    image_digest = _required_string(manifest, "image_digest")
    oci_labels = _string_mapping(manifest.get("oci_labels"), field_name="oci_labels")
    oci_labels["org.opencontainers.image.digest"] = image_digest
    if runtime_env.get("LOTUS_GIT_COMMIT_SHA") != git_commit_sha:
        raise ReleaseEvidenceError("release runtime Git SHA differs from manifest identity")
    if runtime_env.get("LOTUS_IMAGE_VERSION") != git_commit_sha:
        raise ReleaseEvidenceError("release runtime image version differs from manifest identity")
    return ReleaseIdentity(
        service=SERVICE_NAME,
        git_commit_sha=git_commit_sha,
        digest_image_ref=digest_image_ref,
        image_digest=image_digest,
        runtime_env=runtime_env,
        oci_labels=oci_labels,
        sbom_generated=manifest.get("sbom_generated") is True,
        vulnerability_scan_status=str(manifest.get("vulnerability_scan_status", "")),
        image_signed=manifest.get("image_signed") is True,
        provenance_attestation_generated=(manifest.get("provenance_attestation_generated") is True),
    )


def validate_release_pair(
    *,
    candidate_manifest: Mapping[str, Any],
    rollback_manifest: Mapping[str, Any],
) -> tuple[ReleaseIdentity, ReleaseIdentity]:
    """Require distinct, fully qualified candidate and rollback releases."""

    candidate = release_identity(candidate_manifest)
    rollback = release_identity(rollback_manifest)
    if candidate.digest_image_ref == rollback.digest_image_ref:
        raise ReleaseEvidenceError("candidate and rollback releases must use different digests")
    return candidate, rollback


def validate_compose_project_name(project_name: str) -> None:
    """Reject shared, broad, or caller-invented Compose ownership."""

    if project_name in SHARED_COMPOSE_PROJECTS:
        raise ReleaseEvidenceError(f"shared Compose project is forbidden: {project_name}")
    if not project_name.startswith(COMPOSE_PROJECT_PREFIX):
        raise ReleaseEvidenceError(f"Compose project must start with {COMPOSE_PROJECT_PREFIX!r}")
    suffix = project_name.removeprefix(COMPOSE_PROJECT_PREFIX)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{7,63}", suffix):
        raise ReleaseEvidenceError(
            "Compose project suffix must be a bounded lowercase run identity"
        )


def validate_source_identity(*, source_revision: str, source_tree_state: str) -> None:
    """Require one exact clean Git source identity before rehearsal mutation."""

    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ReleaseEvidenceError("source revision must be a full lowercase Git SHA")
    if source_tree_state not in {"clean", "dirty"}:
        raise ReleaseEvidenceError("source tree state must be clean or dirty")


def assert_runtime_matches_release(
    *,
    release: ReleaseIdentity,
    runtime_payload: Mapping[str, Any],
) -> None:
    """Require `/version` evidence to match every release-resolved metadata value."""

    expected = {
        "service_name": release.service,
        "git_commit_sha": release.runtime_env.get("LOTUS_GIT_COMMIT_SHA"),
        "git_branch": release.runtime_env.get("LOTUS_GIT_BRANCH"),
        "build_timestamp": release.runtime_env.get("LOTUS_BUILD_TIMESTAMP"),
        "repo_url": release.runtime_env.get("LOTUS_REPO_URL"),
        "image_version": release.runtime_env.get("LOTUS_IMAGE_VERSION"),
        "image_digest": release.image_digest,
        "ci_pipeline_run_id": release.runtime_env.get("LOTUS_CI_RUN_ID"),
        "oci_labels": dict(release.oci_labels),
    }
    for field_name, expected_value in expected.items():
        actual_value = runtime_payload.get(field_name)
        if actual_value is None or actual_value == "" or actual_value == UNKNOWN_METADATA_VALUE:
            raise ReleaseEvidenceError(f"runtime metadata is unavailable: {field_name}")
        if actual_value != expected_value:
            raise ReleaseEvidenceError(f"runtime metadata differs from release: {field_name}")


def assert_offsets_drained(snapshot: ConsumerGroupSnapshot) -> None:
    """Require an inactive group with exact committed high-watermark parity."""

    if snapshot.active_member_count:
        raise ReleaseEvidenceError(f"consumer group is active: {snapshot.group_id}")
    if not snapshot.partitions:
        raise ReleaseEvidenceError(f"consumer group has no partitions: {snapshot.group_id}")
    for partition in snapshot.partitions:
        if partition.committed_offset < 0:
            raise ReleaseEvidenceError(
                f"consumer offset is uncommitted: {snapshot.group_id} "
                f"{partition.topic}[{partition.partition}]"
            )
        if partition.committed_offset != partition.high_watermark:
            raise ReleaseEvidenceError(
                f"consumer lag is not zero: {snapshot.group_id} "
                f"{partition.topic}[{partition.partition}]"
            )


def assert_offsets_monotonic(
    *,
    before: ConsumerGroupSnapshot,
    after: ConsumerGroupSnapshot,
) -> None:
    """Reject group, partition, high-watermark, or committed-offset regression."""

    if before.group_id != after.group_id:
        raise ReleaseEvidenceError("consumer group identity changed across the rehearsal")
    before_by_key = {(item.topic, item.partition): item for item in before.partitions}
    after_by_key = {(item.topic, item.partition): item for item in after.partitions}
    if set(before_by_key) != set(after_by_key):
        raise ReleaseEvidenceError("consumer partition identity changed across the rehearsal")
    for key, prior in before_by_key.items():
        current = after_by_key[key]
        if current.committed_offset < prior.committed_offset:
            raise ReleaseEvidenceError(f"consumer committed offset moved backwards: {key}")
        if current.high_watermark < prior.high_watermark:
            raise ReleaseEvidenceError(f"consumer high watermark moved backwards: {key}")
        if current.committed_offset > current.high_watermark:
            raise ReleaseEvidenceError(f"consumer offset exceeds high watermark: {key}")


def build_terminal_receipt(
    *,
    receipt_id: str,
    started_at: str,
    ended_at: str,
    source_revision: str,
    source_tree_state: str,
    compose_project: str,
    candidate: ReleaseIdentity,
    rollback: ReleaseIdentity,
    phases: Sequence[PhaseResult],
    invariants: Mapping[str, bool],
    failures: Sequence[str],
    cleanup_owned_resource_count: int | None,
) -> dict[str, Any]:
    """Build, redact, and hash a terminal fail-closed rehearsal receipt."""

    validate_compose_project_name(compose_project)
    validate_source_identity(
        source_revision=source_revision,
        source_tree_state=source_tree_state,
    )
    if cleanup_owned_resource_count is not None and cleanup_owned_resource_count < 0:
        raise ReleaseEvidenceError("cleanup resource count cannot be negative")
    phase_order = tuple(item.phase for item in phases)
    failed_phases = tuple(item.phase.value for item in phases if item.status != "passed")
    missing_invariants = tuple(name for name, passed in invariants.items() if not passed)
    complete_phase_order = phase_order == REQUIRED_PHASE_ORDER
    passed = (
        complete_phase_order
        and not failed_phases
        and bool(invariants)
        and not missing_invariants
        and not failures
        and cleanup_owned_resource_count == 0
        and source_tree_state == "clean"
    )
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": receipt_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "terminal_status": "passed" if passed else "failed",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "cluster_certification": False,
        "source_revision": source_revision,
        "source_tree_state": source_tree_state,
        "candidate_release": asdict(candidate),
        "rollback_release": asdict(rollback),
        "compose_ownership": {
            "project_name": compose_project,
            "owned_resource_count_after_cleanup": cleanup_owned_resource_count,
        },
        "phases": [asdict(item) for item in phases],
        "invariants": dict(invariants),
        "failures": [
            *failures,
            *(f"phase failed: {phase}" for phase in failed_phases),
            *(f"invariant failed: {name}" for name in missing_invariants),
            *(() if complete_phase_order else ("required phase order is incomplete",)),
            *(
                ()
                if cleanup_owned_resource_count == 0
                else ("owned Compose resources remain after cleanup",)
            ),
            *(() if source_tree_state == "clean" else ("source tree is not clean",)),
        ],
    }
    redacted = cast(dict[str, Any], redact_sensitive_values(receipt))
    redacted["receipt_content_hash"] = receipt_content_hash(redacted)
    return redacted


def receipt_content_hash(receipt: Mapping[str, Any]) -> str:
    """Return a deterministic digest excluding the self-referential hash field."""

    return canonical_content_hash(receipt, excluded_fields={"receipt_content_hash"})


def canonical_content_hash(
    payload: Mapping[str, Any],
    *,
    excluded_fields: set[str] | frozenset[str] = frozenset(),
) -> str:
    """Return a deterministic SHA-256 digest for a JSON object."""

    canonical_payload = {key: value for key, value in payload.items() if key not in excluded_fields}
    canonical = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def redact_sensitive_values(value: Any, *, key_name: str = "") -> Any:
    """Recursively redact secret-bearing keys and URI user-info."""

    normalized_key = key_name.lower()
    if any(marker in normalized_key for marker in _SECRET_KEY_MARKERS):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {
            str(key): redact_sensitive_values(item, key_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive_values(item) for item in value]
    if isinstance(value, str):
        return _URI_CREDENTIALS.sub(r"\g<scheme><redacted>@", value)
    return value


def _required_string(manifest: Mapping[str, Any], field_name: str) -> str:
    value = manifest.get(field_name)
    if not isinstance(value, str) or not value.strip() or value == UNKNOWN_METADATA_VALUE:
        raise ReleaseEvidenceError(f"release manifest field is required: {field_name}")
    return value


def _string_mapping(value: Any, *, field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ReleaseEvidenceError(f"release manifest mapping is required: {field_name}")
    if any(not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()):
        raise ReleaseEvidenceError(f"release manifest mapping must contain strings: {field_name}")
    return dict(value)
