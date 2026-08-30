from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Literal

from portfolio_common.ingestion_evidence import (
    IngestionEvidenceBundleIdentityScope,
    IngestionOutcomeCounts,
    build_ingestion_evidence_bundle_id,
    classify_ingestion_outcome,
    derive_source_batch_evidence,
)
from portfolio_common.reconciliation_quality import BLOCKED, COMPLETE, PARTIAL, UNKNOWN
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from src.services.ingestion_service.app.bookkeeping_recovery import (
    POST_BOOKKEEPING_FAILURE_PHASES,
)
from src.services.ingestion_service.app.DTOs.ingestion_job_dto import (
    ConsumerDlqEventResponse,
    IngestionEvidenceBundleResponse,
    IngestionEvidenceRetentionPosture,
    IngestionEvidenceValidationSummary,
    IngestionJobFailureResponse,
    IngestionJobResponse,
    IngestionReplayAuditResponse,
)

from ..application.replay_recovery_policy import derive_consumer_dlq_recovery

_EVIDENCE_LIMIT = 500
_DEFAULT_RETENTION_CLASS = "governed_operational_evidence"
_DEFAULT_ARCHIVAL_POSTURE = "policy_managed"

ReplayPosture = Literal[
    "not_requested",
    "dry_run_only",
    "replayed",
    "replay_failed",
    "replay_bookkeeping_failed",
]
RepairPosture = Literal["not_required", "required", "repaired", "unknown"]


@dataclass(frozen=True)
class IngestionEvidenceBundleBuilder:
    retention_class: str = _DEFAULT_RETENTION_CLASS
    archival_posture: str = _DEFAULT_ARCHIVAL_POSTURE
    retention_period_days: int | None = None

    def build(
        self,
        *,
        job: IngestionJobResponse,
        failures: list[IngestionJobFailureResponse],
        replay_audits: list[IngestionReplayAuditResponse],
        consumer_dlq_events: list[ConsumerDlqEventResponse],
        request_payload: dict[str, Any] | None,
        evidence_complete: bool = True,
    ) -> IngestionEvidenceBundleResponse:
        counts = _outcome_counts(
            job=job,
            failures=failures,
            consumer_dlq_events=consumer_dlq_events,
        )
        source_batch = derive_source_batch_evidence(
            request_payload,
            payload_kind=job.entity_type,
            tenant_id=job.tenant_id,
        )
        validation_findings = _validation_finding_references(
            failures=failures,
            consumer_dlq_events=consumer_dlq_events,
        )
        evidence_references = _evidence_references(
            job=job,
            failures=failures,
            replay_audits=replay_audits,
            consumer_dlq_events=consumer_dlq_events,
        )
        source_refs = _source_references(source_batch)
        bundle_id = build_ingestion_evidence_bundle_id(
            IngestionEvidenceBundleIdentityScope(
                job_id=job.job_id,
                endpoint=job.endpoint,
                entity_type=job.entity_type,
                accepted_count=job.accepted_count,
                job_state=_job_state_identity(job),
                request_payload_fingerprint=job.request_payload_fingerprint,
                failure_ids=tuple(failure.failure_id for failure in failures),
                replay_ids=tuple(audit.replay_id for audit in replay_audits),
                consumer_dlq_event_ids=tuple(event.event_id for event in consumer_dlq_events),
            )
        )
        outcome = classify_ingestion_outcome(counts)
        replay_posture = _replay_posture(replay_audits)
        consumer_dlq_recovery = derive_consumer_dlq_recovery(
            events=consumer_dlq_events,
            replay_audits=replay_audits,
            evidence_complete=evidence_complete,
        )
        repair_posture = _repair_posture(job=job, failures=failures)
        evidence_gate, evidence_gate_reasons = _evidence_gate(
            job_status=job.status,
            outcome=outcome,
            replay_posture=replay_posture,
            repair_posture=repair_posture,
            evidence_complete=evidence_complete,
            consumer_dlq_events=consumer_dlq_events,
            unresolved_consumer_dlq_event_ids={
                recovery.event_id
                for recovery in consumer_dlq_recovery
                if recovery.state != "recovered"
            },
        )
        validation = IngestionEvidenceValidationSummary(
            profile_name=_unambiguous_payload_value(
                request_payload,
                keys=("validation_profile", "validation_profile_name"),
            ),
            profile_version=_unambiguous_payload_value(
                request_payload,
                keys=("validation_profile_version", "schema_version"),
            ),
            received_count=(
                counts.accepted_count + counts.rejected_count + counts.quarantined_count
            ),
            accepted_count=counts.accepted_count,
            rejected_count=counts.rejected_count,
            quarantined_count=counts.quarantined_count,
            finding_count=len(validation_findings),
            finding_references=validation_findings,
        )
        retention = IngestionEvidenceRetentionPosture(
            retention_class=self.retention_class,
            archival_posture=self.archival_posture,
            retention_period_days=self.retention_period_days,
        )
        latest_evidence_timestamp = _latest_evidence_timestamp(
            job=job,
            failures=failures,
            replay_audits=replay_audits,
            consumer_dlq_events=consumer_dlq_events,
        )
        content_hash = stable_content_hash(
            {
                "bundle_id": bundle_id,
                "consumer_dlq_events": [
                    event.model_dump(mode="json") for event in consumer_dlq_events
                ],
                "evidence_complete": evidence_complete,
                "evidence_gate": evidence_gate,
                "evidence_gate_reasons": evidence_gate_reasons,
                "failures": [failure.model_dump(mode="json") for failure in failures],
                "job": job.model_dump(mode="json"),
                "outcome": outcome,
                "repair_posture": repair_posture,
                "replay_audits": [audit.model_dump(mode="json") for audit in replay_audits],
                "replay_posture": replay_posture,
                "retention": retention.model_dump(mode="json"),
                "source_refs": source_refs,
                "validation": validation.model_dump(mode="json"),
            }
        )
        runtime_metadata = source_data_product_runtime_metadata(
            as_of_date=job.submitted_at.date(),
            generated_at=datetime.now(UTC),
            reconciliation_status=UNKNOWN,
            data_quality_status=_data_quality_status(
                outcome=outcome,
                evidence_complete=evidence_complete,
            ),
            latest_evidence_timestamp=latest_evidence_timestamp,
            source_batch_fingerprint=(
                source_batch.source_batch_fingerprint if source_batch is not None else None
            ),
            snapshot_id=bundle_id,
            policy_version="ingestion-evidence.v1",
            content_hash=content_hash,
            source_refs=source_refs + evidence_references,
            lineage={
                "source_product": "IngestionEvidenceBundle",
                "source_owner": "lotus-core",
                "ingestion_job_id": job.job_id,
                "ingestion_correlation_id": job.correlation_id,
            },
            source_evidence_current=False,
            freshness_status="UNAVAILABLE",
        )
        return IngestionEvidenceBundleResponse(
            **runtime_metadata,
            evidence_bundle_id=bundle_id,
            ingestion_outcome=outcome,
            replay_posture=replay_posture,
            repair_posture=repair_posture,
            source_system=source_batch.source_system if source_batch is not None else None,
            source_batch_id=source_batch.source_batch_id if source_batch is not None else None,
            evidence_references=evidence_references,
            evidence_complete=evidence_complete,
            evidence_limit=_EVIDENCE_LIMIT,
            evidence_gate=evidence_gate,
            evidence_gate_reasons=evidence_gate_reasons,
            validation=validation,
            retention=retention,
            job=job,
            failures=failures,
            consumer_dlq_events=consumer_dlq_events,
            replay_audits=replay_audits,
        )


def _outcome_counts(
    *,
    job: IngestionJobResponse,
    failures: Iterable[IngestionJobFailureResponse],
    consumer_dlq_events: Iterable[ConsumerDlqEventResponse],
) -> IngestionOutcomeCounts:
    quarantined_keys = {
        event.original_key or f"event:{event.event_id}"
        for event in consumer_dlq_events
        if _is_explicit_quarantine_event(event)
    }
    quarantined_count = min(job.accepted_count, len(quarantined_keys))
    rejected_keys: set[str] = set()
    if job.status == "failed":
        for failure in failures:
            if failure.failure_phase in POST_BOOKKEEPING_FAILURE_PHASES:
                continue
            rejected_keys.update(failure.failed_record_keys)
        if rejected_keys:
            rejected_count = min(
                max(job.accepted_count - quarantined_count, 0),
                len(rejected_keys - quarantined_keys),
            )
        else:
            rejected_count = max(job.accepted_count - quarantined_count, 0)
    else:
        rejected_count = 0
    accepted_count = max(job.accepted_count - rejected_count - quarantined_count, 0)
    return IngestionOutcomeCounts(
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        quarantined_count=quarantined_count,
    )


def _replay_posture(audits: Iterable[IngestionReplayAuditResponse]) -> ReplayPosture:
    audit_rows = list(audits)
    if not audit_rows:
        return "not_requested"
    latest_status = audit_rows[0].replay_status
    if latest_status == "replayed_bookkeeping_failed":
        return "replay_bookkeeping_failed"
    if latest_status == "replayed":
        return "replayed"
    if latest_status in {"failed", "not_replayable"}:
        return "replay_failed"
    if latest_status == "duplicate_blocked":
        latest = audit_rows[0]
        return (
            "replayed"
            if any(
                audit.replay_status == "replayed"
                and audit.recovery_path == latest.recovery_path
                and audit.event_id == latest.event_id
                and audit.replay_fingerprint == latest.replay_fingerprint
                for audit in audit_rows[1:]
            )
            else "replay_failed"
        )
    if latest_status == "dry_run":
        return "dry_run_only"
    return "replay_failed"


def _repair_posture(
    *,
    job: IngestionJobResponse,
    failures: Iterable[IngestionJobFailureResponse],
) -> RepairPosture:
    has_bookkeeping_failure = any(
        failure.failure_phase in POST_BOOKKEEPING_FAILURE_PHASES for failure in failures
    )
    if not has_bookkeeping_failure:
        return "not_required"
    if job.status == "accepted":
        return "required"
    return "unknown"


def _is_explicit_quarantine_event(event: ConsumerDlqEventResponse) -> bool:
    reason_code = event.error_reason_code.strip().upper()
    return "QUARANTIN" in reason_code or "VALIDATION" in reason_code


def _evidence_gate(
    *,
    job_status: str,
    outcome: str,
    replay_posture: ReplayPosture,
    repair_posture: RepairPosture,
    evidence_complete: bool,
    consumer_dlq_events: Iterable[ConsumerDlqEventResponse],
    unresolved_consumer_dlq_event_ids: set[str],
) -> tuple[Literal["ALLOW", "BLOCK", "REVIEW_REQUIRED"], list[str]]:
    reasons: set[str] = set()
    if job_status == "failed":
        reasons.add("INGESTION_JOB_FAILED")
    elif job_status == "accepted":
        reasons.add("INGESTION_JOB_PENDING")
    if not evidence_complete:
        reasons.add("EVIDENCE_LIMIT_EXCEEDED")
    if outcome == "partially_accepted":
        reasons.add("PARTIALLY_ACCEPTED_SOURCE_BATCH")
    elif outcome == "rejected":
        reasons.add("REJECTED_SOURCE_BATCH")
    elif outcome == "quarantined":
        reasons.add("QUARANTINED_SOURCE_BATCH")
    elif outcome == "empty":
        reasons.add("EMPTY_SOURCE_BATCH")
    if any(
        event.event_id in unresolved_consumer_dlq_event_ids
        and not _is_explicit_quarantine_event(event)
        for event in consumer_dlq_events
    ):
        reasons.add("CORRELATED_PROCESSING_FAILURE")
    if replay_posture in {"replay_failed", "replay_bookkeeping_failed"}:
        reasons.add("REPLAY_RECOVERY_INCOMPLETE")
    if repair_posture == "required":
        reasons.add("BOOKKEEPING_REPAIR_REQUIRED")
    elif repair_posture == "unknown":
        reasons.add("BOOKKEEPING_REPAIR_UNPROVEN")
    ordered_reasons = sorted(reasons)
    blocking_reasons = {
        "PARTIALLY_ACCEPTED_SOURCE_BATCH",
        "REJECTED_SOURCE_BATCH",
        "QUARANTINED_SOURCE_BATCH",
        "CORRELATED_PROCESSING_FAILURE",
        "REPLAY_RECOVERY_INCOMPLETE",
        "BOOKKEEPING_REPAIR_REQUIRED",
        "INGESTION_JOB_FAILED",
    }
    if set(ordered_reasons).intersection(blocking_reasons):
        return "BLOCK", ordered_reasons
    if ordered_reasons:
        return "REVIEW_REQUIRED", ordered_reasons
    return "ALLOW", []


def _data_quality_status(*, outcome: str, evidence_complete: bool) -> str:
    if not evidence_complete:
        return UNKNOWN
    if outcome == "accepted":
        return COMPLETE
    if outcome == "partially_accepted":
        return PARTIAL
    if outcome in {"rejected", "quarantined"}:
        return BLOCKED
    return UNKNOWN


def _validation_finding_references(
    *,
    failures: Iterable[IngestionJobFailureResponse],
    consumer_dlq_events: Iterable[ConsumerDlqEventResponse],
) -> list[str]:
    references = {
        f"ingestion-failure:{failure.failure_id}"
        for failure in failures
        if "validat" in failure.failure_phase.lower()
    }
    references.update(
        f"consumer-dlq:{event.event_id}"
        for event in consumer_dlq_events
        if "VALIDATION" in event.error_reason_code.upper()
    )
    return sorted(references)


def _evidence_references(
    *,
    job: IngestionJobResponse,
    failures: Iterable[IngestionJobFailureResponse],
    replay_audits: Iterable[IngestionReplayAuditResponse],
    consumer_dlq_events: Iterable[ConsumerDlqEventResponse],
) -> list[str]:
    references = {f"ingestion-job:{job.job_id}"}
    references.update(f"ingestion-failure:{failure.failure_id}" for failure in failures)
    references.update(f"ingestion-replay:{audit.replay_id}" for audit in replay_audits)
    references.update(f"consumer-dlq:{event.event_id}" for event in consumer_dlq_events)
    return sorted(references)


def _source_references(source_batch) -> list[str]:
    if source_batch is None:
        return []
    references = {
        f"source-system:{source_batch.source_system}",
        f"source-batch:{source_batch.source_system}:{source_batch.source_batch_id}",
    }
    references.update(
        f"source-record:{source_batch.source_system}:{key}"
        for key in source_batch.source_record_keys
    )
    return sorted(references)


def _job_state_identity(job: IngestionJobResponse) -> str:
    return "|".join(
        (
            job.status,
            str(job.retry_count),
            job.completed_at.isoformat() if job.completed_at is not None else "",
            job.last_retried_at.isoformat() if job.last_retried_at is not None else "",
            job.failure_code or "",
        )
    )


def _latest_evidence_timestamp(
    *,
    job: IngestionJobResponse,
    failures: Iterable[IngestionJobFailureResponse],
    replay_audits: Iterable[IngestionReplayAuditResponse],
    consumer_dlq_events: Iterable[ConsumerDlqEventResponse],
) -> datetime:
    timestamps = [job.submitted_at]
    timestamps.extend(
        timestamp for timestamp in (job.completed_at, job.last_retried_at) if timestamp is not None
    )
    timestamps.extend(failure.failed_at for failure in failures)
    timestamps.extend(event.observed_at for event in consumer_dlq_events)
    for audit in replay_audits:
        timestamps.append(audit.requested_at)
        if audit.completed_at is not None:
            timestamps.append(audit.completed_at)
    return max(timestamps)


def _unambiguous_payload_value(
    payload: dict[str, Any] | None,
    *,
    keys: tuple[str, ...],
) -> str | None:
    if payload is None:
        return None
    values = {
        cleaned
        for value in _nested_values(payload, keys)
        if isinstance(value, str) and (cleaned := value.strip())
    }
    return next(iter(values)) if len(values) == 1 else None


def _nested_values(value: Any, keys: tuple[str, ...]):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key in keys:
                yield nested_value
            yield from _nested_values(nested_value, keys)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _nested_values(nested_value, keys)
