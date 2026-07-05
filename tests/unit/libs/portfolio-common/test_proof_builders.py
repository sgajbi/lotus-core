from datetime import UTC, datetime

import pytest
from portfolio_common.proof_builders import (
    BLOCKED,
    PARTIAL,
    READY,
    AppValidationEvidenceProofInput,
    IngestionReplayEvidenceProofInput,
    ReconciliationEvidenceProofInput,
    SourceDataSupportabilityProofInput,
    build_app_validation_evidence_proof,
    build_ingestion_replay_evidence_proof,
    build_reconciliation_evidence_proof,
    build_source_data_supportability_proof,
)

GENERATED_AT = datetime(2026, 7, 5, 10, 15, tzinfo=UTC)


def test_source_data_supportability_proof_uses_typed_input_without_runtime_clients() -> None:
    artifact = build_source_data_supportability_proof(
        SourceDataSupportabilityProofInput(
            product_name="PortfolioStateSnapshot:v1",
            scope_id="portfolio:PB_SG_GLOBAL_BAL_001",
            supportability_status="ready",
            generated_at=GENERATED_AT,
            reason_codes=("SOURCE_DATA_READY",),
            latest_evidence_timestamp=datetime(2026, 7, 5, 9, 45, tzinfo=UTC),
            lineage={"source_table": "portfolio_snapshots"},
            contract_artifacts=("contracts/source-data-products/portfolio-state-snapshot.v1.json",),
        )
    )

    assert artifact.proof_type == "source_data_supportability"
    assert artifact.subject_id == "portfolio:PB_SG_GLOBAL_BAL_001"
    assert artifact.status == READY
    assert artifact.observations[0].summary == "SOURCE_DATA_READY"
    assert artifact.lineage["source_table"] == "portfolio_snapshots"
    assert artifact.diagnostics["product_name"] == "PortfolioStateSnapshot:v1"


def test_ingestion_replay_proof_fails_closed_when_audit_is_missing() -> None:
    artifact = build_ingestion_replay_evidence_proof(
        IngestionReplayEvidenceProofInput(
            replay_id="replay-001",
            replay_status="accepted",
            generated_at=GENERATED_AT,
            audit_required=True,
            audit_recorded=False,
            replay_fingerprint="replayfp_001",
            correlation_id="corr-001",
            failure_reason="audit_store_unavailable",
        )
    )

    assert artifact.proof_type == "ingestion_replay_evidence"
    assert artifact.status == BLOCKED
    assert artifact.observations[1].summary == "audit_missing"
    assert artifact.lineage["correlation_id"] == "corr-001"


def test_reconciliation_proof_blocks_on_blocking_findings() -> None:
    artifact = build_reconciliation_evidence_proof(
        ReconciliationEvidenceProofInput(
            run_id="recon-run-001",
            run_status="COMPLETED",
            generated_at=GENERATED_AT,
            finding_count=3,
            blocking_finding_count=1,
            warning_count=0,
            lineage={"portfolio_id": "PB_SG_GLOBAL_BAL_001"},
        )
    )

    assert artifact.proof_type == "reconciliation_evidence"
    assert artifact.status == BLOCKED
    assert artifact.diagnostics["blocking_finding_count"] == 1
    assert artifact.lineage["portfolio_id"] == "PB_SG_GLOBAL_BAL_001"


def test_app_validation_proof_classifies_warnings_as_partial() -> None:
    artifact = build_app_validation_evidence_proof(
        AppValidationEvidenceProofInput(
            validation_run_id="local-validation-001",
            generated_at=GENERATED_AT,
            command="make architecture-guard",
            passed_checks=21,
            failed_checks=0,
            warning_count=2,
            artifact_paths=("output/lotus-core-validation/summary.json",),
        )
    )

    assert artifact.proof_type == "app_validation_evidence"
    assert artifact.status == PARTIAL
    assert artifact.observations[0].evidence_refs == ("output/lotus-core-validation/summary.json",)


def test_proof_builders_reject_naive_generated_at() -> None:
    with pytest.raises(ValueError, match="generated_at must be timezone-aware"):
        build_app_validation_evidence_proof(
            AppValidationEvidenceProofInput(
                validation_run_id="local-validation-001",
                generated_at=datetime(2026, 7, 5, 10, 15),
                command="make architecture-guard",
                passed_checks=1,
                failed_checks=0,
            )
        )
