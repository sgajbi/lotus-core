"""Typed in-process proof-builder contracts for evidence-producing capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

SOURCE_DATA_SUPPORTABILITY_PROOF = "source_data_supportability"
INGESTION_REPLAY_EVIDENCE_PROOF = "ingestion_replay_evidence"
RECONCILIATION_EVIDENCE_PROOF = "reconciliation_evidence"
APP_VALIDATION_EVIDENCE_PROOF = "app_validation_evidence"

READY = "ready"
PARTIAL = "partial"
BLOCKED = "blocked"
UNKNOWN = "unknown"

_BLOCKING_RECONCILIATION_STATUSES = {"FAILED", "REQUIRES_REPLAY", "BLOCKED"}
_READY_RECONCILIATION_STATUSES = {"COMPLETE", "COMPLETED", "READY"}


@dataclass(frozen=True, slots=True)
class ProofObservation:
    name: str
    status: str
    summary: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProofArtifact:
    proof_type: str
    subject_id: str
    status: str
    generated_at: datetime
    observations: tuple[ProofObservation, ...]
    lineage: Mapping[str, str] = field(default_factory=dict)
    contract_artifacts: tuple[str, ...] = ()
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "lineage", MappingProxyType(dict(self.lineage)))
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))


@dataclass(frozen=True, slots=True)
class SourceDataSupportabilityProofInput:
    product_name: str
    scope_id: str
    supportability_status: str
    generated_at: datetime
    reason_codes: tuple[str, ...] = ()
    latest_evidence_timestamp: datetime | None = None
    lineage: Mapping[str, str] = field(default_factory=dict)
    contract_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IngestionReplayEvidenceProofInput:
    replay_id: str
    replay_status: str
    generated_at: datetime
    audit_required: bool
    audit_recorded: bool
    replay_fingerprint: str
    correlation_id: str | None = None
    failure_reason: str | None = None
    contract_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReconciliationEvidenceProofInput:
    run_id: str
    run_status: str
    generated_at: datetime
    finding_count: int
    blocking_finding_count: int
    warning_count: int = 0
    contract_artifacts: tuple[str, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AppValidationEvidenceProofInput:
    validation_run_id: str
    generated_at: datetime
    command: str
    passed_checks: int
    failed_checks: int
    warning_count: int = 0
    artifact_paths: tuple[str, ...] = ()
    contract_artifacts: tuple[str, ...] = ()


def build_source_data_supportability_proof(
    proof_input: SourceDataSupportabilityProofInput,
) -> ProofArtifact:
    status = _normalize_status(proof_input.supportability_status)
    observation = ProofObservation(
        name="source_data_supportability",
        status=status,
        summary=";".join(proof_input.reason_codes) if proof_input.reason_codes else status,
    )
    diagnostics: dict[str, object] = {
        "product_name": _require_text(proof_input.product_name, "product_name"),
        "reason_codes": proof_input.reason_codes,
    }
    if proof_input.latest_evidence_timestamp is not None:
        diagnostics["latest_evidence_timestamp"] = proof_input.latest_evidence_timestamp.isoformat()
    return _artifact(
        proof_type=SOURCE_DATA_SUPPORTABILITY_PROOF,
        subject_id=proof_input.scope_id,
        status=status,
        generated_at=proof_input.generated_at,
        observations=(observation,),
        lineage=proof_input.lineage,
        contract_artifacts=proof_input.contract_artifacts,
        diagnostics=diagnostics,
    )


def build_ingestion_replay_evidence_proof(
    proof_input: IngestionReplayEvidenceProofInput,
) -> ProofArtifact:
    status = _normalize_status(proof_input.replay_status)
    if proof_input.audit_required and not proof_input.audit_recorded:
        status = BLOCKED
    observations = (
        ProofObservation(
            name="replay_status",
            status=status,
            summary=status,
            evidence_refs=(proof_input.replay_fingerprint,),
        ),
        ProofObservation(
            name="replay_audit",
            status=READY if proof_input.audit_recorded else BLOCKED,
            summary="audit_recorded" if proof_input.audit_recorded else "audit_missing",
        ),
    )
    return _artifact(
        proof_type=INGESTION_REPLAY_EVIDENCE_PROOF,
        subject_id=proof_input.replay_id,
        status=status,
        generated_at=proof_input.generated_at,
        observations=observations,
        lineage=_compact_mapping({"correlation_id": proof_input.correlation_id}),
        contract_artifacts=proof_input.contract_artifacts,
        diagnostics=_compact_mapping(
            {
                "audit_required": proof_input.audit_required,
                "audit_recorded": proof_input.audit_recorded,
                "failure_reason": proof_input.failure_reason,
                "replay_fingerprint": proof_input.replay_fingerprint,
            }
        ),
    )


def build_reconciliation_evidence_proof(
    proof_input: ReconciliationEvidenceProofInput,
) -> ProofArtifact:
    _require_non_negative(proof_input.finding_count, "finding_count")
    _require_non_negative(proof_input.blocking_finding_count, "blocking_finding_count")
    _require_non_negative(proof_input.warning_count, "warning_count")
    status = _classify_reconciliation_proof_status(proof_input)
    observations = (
        ProofObservation(
            name="reconciliation_run",
            status=status,
            summary=_require_text(proof_input.run_status, "run_status").upper(),
        ),
        ProofObservation(
            name="reconciliation_findings",
            status=BLOCKED if proof_input.blocking_finding_count else READY,
            summary=str(proof_input.finding_count),
        ),
    )
    return _artifact(
        proof_type=RECONCILIATION_EVIDENCE_PROOF,
        subject_id=proof_input.run_id,
        status=status,
        generated_at=proof_input.generated_at,
        observations=observations,
        lineage=proof_input.lineage,
        contract_artifacts=proof_input.contract_artifacts,
        diagnostics={
            "finding_count": proof_input.finding_count,
            "blocking_finding_count": proof_input.blocking_finding_count,
            "warning_count": proof_input.warning_count,
        },
    )


def build_app_validation_evidence_proof(
    proof_input: AppValidationEvidenceProofInput,
) -> ProofArtifact:
    _require_non_negative(proof_input.passed_checks, "passed_checks")
    _require_non_negative(proof_input.failed_checks, "failed_checks")
    _require_non_negative(proof_input.warning_count, "warning_count")
    status = _classify_validation_status(proof_input)
    return _artifact(
        proof_type=APP_VALIDATION_EVIDENCE_PROOF,
        subject_id=proof_input.validation_run_id,
        status=status,
        generated_at=proof_input.generated_at,
        observations=(
            ProofObservation(
                name="validation_command",
                status=status,
                summary=_require_text(proof_input.command, "command"),
                evidence_refs=proof_input.artifact_paths,
            ),
        ),
        contract_artifacts=proof_input.contract_artifacts,
        diagnostics={
            "passed_checks": proof_input.passed_checks,
            "failed_checks": proof_input.failed_checks,
            "warning_count": proof_input.warning_count,
        },
    )


def _artifact(
    *,
    proof_type: str,
    subject_id: str,
    status: str,
    generated_at: datetime,
    observations: tuple[ProofObservation, ...],
    lineage: Mapping[str, str] | None = None,
    contract_artifacts: tuple[str, ...] = (),
    diagnostics: Mapping[str, object] | None = None,
) -> ProofArtifact:
    _require_text(proof_type, "proof_type")
    _require_text(subject_id, "subject_id")
    if not observations:
        raise ValueError("observations are required")
    _require_timezone_aware(generated_at)
    return ProofArtifact(
        proof_type=proof_type,
        subject_id=subject_id,
        status=_normalize_status(status),
        generated_at=generated_at,
        observations=observations,
        lineage=lineage or {},
        contract_artifacts=contract_artifacts,
        diagnostics=diagnostics or {},
    )


def _classify_reconciliation_proof_status(
    proof_input: ReconciliationEvidenceProofInput,
) -> str:
    run_status = _require_text(proof_input.run_status, "run_status").upper()
    if run_status in _BLOCKING_RECONCILIATION_STATUSES or proof_input.blocking_finding_count > 0:
        return BLOCKED
    if proof_input.warning_count > 0:
        return PARTIAL
    if run_status in _READY_RECONCILIATION_STATUSES:
        return READY
    return UNKNOWN


def _classify_validation_status(proof_input: AppValidationEvidenceProofInput) -> str:
    if proof_input.failed_checks > 0:
        return BLOCKED
    if proof_input.warning_count > 0:
        return PARTIAL
    if proof_input.passed_checks > 0:
        return READY
    return UNKNOWN


def _normalize_status(value: str) -> str:
    normalized = _require_text(value, "status").strip().lower()
    return normalized.replace("_", "-").replace(" ", "-")


def _compact_mapping(values: Mapping[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


def _require_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_timezone_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
