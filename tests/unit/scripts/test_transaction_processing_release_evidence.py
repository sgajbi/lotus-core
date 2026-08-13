from dataclasses import replace

import pytest

from scripts.operations.transaction_processing_cutover_offsets import (
    ConsumerGroupSnapshot,
    PartitionOffset,
)
from scripts.operations.transaction_processing_release_evidence import (
    COMPOSE_PROJECT_PREFIX,
    FinancialEffectEvidence,
    PhaseResult,
    RehearsalPhase,
    ReleaseEvidenceError,
    assert_offsets_drained,
    assert_offsets_monotonic,
    assert_runtime_matches_release,
    build_terminal_receipt,
    receipt_content_hash,
    redact_sensitive_values,
    validate_compose_project_name,
    validate_release_pair,
)
from scripts.release.write_image_release_manifest import build_release_manifest

CANDIDATE_SHA = "a" * 40
ROLLBACK_SHA = "b" * 40
CANDIDATE_DIGEST = "sha256:" + "c" * 64
ROLLBACK_DIGEST = "sha256:" + "d" * 64


def _manifest(*, sha: str, digest: str) -> dict[str, object]:
    image_ref = "ghcr.io/sgajbi/lotus-core/portfolio-transaction-processing-service"
    subject = {"image_ref": image_ref, "image_digest": digest}
    source = {
        "repository": "sgajbi/lotus-core",
        "git_commit_sha": sha,
        "ci_run_id": "31365245365",
        "ci_run_attempt": "1",
    }
    digest_ref = f"{image_ref}@{digest}"
    return build_release_manifest(
        service="portfolio_transaction_processing_service",
        image_name="portfolio-transaction-processing-service",
        image_ref=image_ref,
        image_tag=f"{image_ref}:{sha}",
        image_digest=digest,
        git_commit_sha=sha,
        git_branch="main",
        image_version=sha,
        build_timestamp="2026-08-10T07:00:00Z",
        repo_url="https://github.com/sgajbi/lotus-core",
        repository="sgajbi/lotus-core",
        ci_pipeline_run_id="31365245365",
        ci_run_attempt="1",
        scan_receipt={
            "subject": {
                "service": "portfolio_transaction_processing_service",
                **subject,
                "digest_image_ref": digest_ref,
            },
            "source": source,
            "policy": {"decision": "passed"},
        },
        sbom={"subject": subject},
        signature_verification={"subject": subject},
        provenance_verification={"subject": subject},
        base_image={
            "dockerfile": "src/services/portfolio_transaction_processing_service/Dockerfile"
        },
        promotion_receipts=[
            {
                "environment": environment,
                "image_ref": digest_ref,
                "receipt_sha256": "sha256:" + str(index) * 64,
            }
            for index, environment in enumerate(("dev", "uat", "prod"), start=1)
        ],
    )


def _release_pair():
    return validate_release_pair(
        candidate_manifest=_manifest(sha=CANDIDATE_SHA, digest=CANDIDATE_DIGEST),
        rollback_manifest=_manifest(sha=ROLLBACK_SHA, digest=ROLLBACK_DIGEST),
    )


def _snapshot(*, committed: int = 10, high: int = 10, active: int = 0):
    return ConsumerGroupSnapshot(
        group_id="portfolio_transaction_processing_group",
        active_member_count=active,
        partitions=(
            PartitionOffset(
                topic="transactions.persisted",
                partition=0,
                committed_offset=committed,
                high_watermark=high,
            ),
        ),
    )


def _phases() -> tuple[PhaseResult, ...]:
    return tuple(
        PhaseResult(
            phase=phase,
            status="passed",
            started_at="2026-08-10T07:00:00Z",
            ended_at="2026-08-10T07:00:01Z",
            evidence={"phase": phase.value},
        )
        for phase in RehearsalPhase
    )


def test_release_pair_requires_distinct_qualified_digests() -> None:
    candidate, rollback = _release_pair()

    assert candidate.git_commit_sha == CANDIDATE_SHA
    assert candidate.runtime_service_name == "portfolio_transaction_processing_service_web"
    assert rollback.git_commit_sha == ROLLBACK_SHA

    with pytest.raises(ReleaseEvidenceError, match="different digests"):
        validate_release_pair(
            candidate_manifest=_manifest(sha=CANDIDATE_SHA, digest=CANDIDATE_DIGEST),
            rollback_manifest=_manifest(sha=CANDIDATE_SHA, digest=CANDIDATE_DIGEST),
        )


def test_runtime_metadata_must_match_release_manifest_exactly() -> None:
    candidate, _ = _release_pair()
    runtime = {
        "service_name": candidate.runtime_service_name,
        "git_commit_sha": CANDIDATE_SHA,
        "git_branch": "main",
        "build_timestamp": "2026-08-10T07:00:00Z",
        "repo_url": "https://github.com/sgajbi/lotus-core",
        "image_version": CANDIDATE_SHA,
        "image_digest": CANDIDATE_DIGEST,
        "ci_pipeline_run_id": "31365245365",
        "oci_labels": dict(candidate.oci_labels),
    }

    assert_runtime_matches_release(release=candidate, runtime_payload=runtime)

    with pytest.raises(ReleaseEvidenceError, match="image_digest"):
        assert_runtime_matches_release(
            release=candidate,
            runtime_payload={**runtime, "image_digest": ROLLBACK_DIGEST},
        )
    with pytest.raises(ReleaseEvidenceError, match="git_branch"):
        assert_runtime_matches_release(
            release=candidate,
            runtime_payload={**runtime, "git_branch": "unknown"},
        )
    with pytest.raises(ReleaseEvidenceError, match="service_name"):
        assert_runtime_matches_release(
            release=candidate,
            runtime_payload={**runtime, "service_name": candidate.service},
        )


def test_compose_ownership_rejects_shared_or_unbounded_projects() -> None:
    validate_compose_project_name(COMPOSE_PROJECT_PREFIX + "20260810-070000-a1b2c3d4")

    for invalid in ("lotus-core-app-local", "lotus-core-canonical-ui", "custom-project"):
        with pytest.raises(ReleaseEvidenceError):
            validate_compose_project_name(invalid)


def test_offset_evidence_requires_drain_and_monotonic_progress() -> None:
    before = _snapshot(committed=10, high=10)
    after = _snapshot(committed=15, high=15)

    assert_offsets_drained(before)
    assert_offsets_monotonic(before=before, after=after)

    with pytest.raises(ReleaseEvidenceError, match="active"):
        assert_offsets_drained(_snapshot(active=1))
    with pytest.raises(ReleaseEvidenceError, match="lag is not zero"):
        assert_offsets_drained(_snapshot(committed=9, high=10))
    with pytest.raises(ReleaseEvidenceError, match="moved backwards"):
        assert_offsets_monotonic(before=after, after=before)


def test_financial_effect_evidence_fails_closed() -> None:
    evidence = FinancialEffectEvidence(
        expected_transactions=10,
        persisted_transactions=10,
        expected_positions=10,
        persisted_positions=10,
        pending_outbox=0,
        failed_outbox=0,
        dlq_count=0,
        duplicate_financial_effects=0,
        reconciliation_findings=0,
        unresolved_work=0,
    )

    assert evidence.findings() == ()
    assert replace(evidence, failed_outbox=1).findings() == ("failed_outbox must be zero",)


def test_terminal_receipt_passes_only_with_complete_clean_evidence() -> None:
    candidate, rollback = _release_pair()
    receipt = build_terminal_receipt(
        receipt_id="release-rehearsal-20260810-070000",
        started_at="2026-08-10T07:00:00Z",
        ended_at="2026-08-10T07:05:00Z",
        source_revision=CANDIDATE_SHA,
        source_tree_state="clean",
        compose_project=COMPOSE_PROJECT_PREFIX + "20260810-070000-a1b2c3d4",
        candidate=candidate,
        rollback=rollback,
        phases=_phases(),
        invariants={"candidate_reconciled": True, "rollback_reconciled": True},
        failures=(),
        cleanup_owned_resource_count=0,
    )

    assert receipt["terminal_status"] == "passed"
    assert receipt["cluster_certification"] is False
    assert receipt["receipt_content_hash"] == receipt_content_hash(receipt)


@pytest.mark.parametrize(
    ("phases", "invariants", "failures", "cleanup", "tree_state"),
    [
        (_phases()[:-1], {"complete": True}, (), 0, "clean"),
        (_phases(), {"complete": False}, (), 0, "clean"),
        (_phases(), {"complete": True}, ("canary mismatch",), 0, "clean"),
        (_phases(), {"complete": True}, (), 1, "clean"),
        (_phases(), {"complete": True}, (), 0, "dirty"),
    ],
)
def test_terminal_receipt_fails_closed_for_incomplete_evidence(
    phases,
    invariants,
    failures,
    cleanup,
    tree_state,
) -> None:
    candidate, rollback = _release_pair()

    receipt = build_terminal_receipt(
        receipt_id="release-rehearsal-20260810-070000",
        started_at="2026-08-10T07:00:00Z",
        ended_at="2026-08-10T07:05:00Z",
        source_revision=CANDIDATE_SHA,
        source_tree_state=tree_state,
        compose_project=COMPOSE_PROJECT_PREFIX + "20260810-070000-a1b2c3d4",
        candidate=candidate,
        rollback=rollback,
        phases=phases,
        invariants=invariants,
        failures=failures,
        cleanup_owned_resource_count=cleanup,
    )

    assert receipt["terminal_status"] == "failed"
    assert receipt["failures"]


def test_receipt_redaction_covers_secret_keys_and_uri_credentials() -> None:
    redacted = redact_sensitive_values(
        {
            "database_url": "postgresql://lotus:unsafe@localhost/core",
            "access_token": "unsafe-token",
            "nested": {"password": "unsafe-password"},
        }
    )

    assert redacted == {
        "database_url": "postgresql://<redacted>@localhost/core",
        "access_token": "<redacted>",
        "nested": {"password": "<redacted>"},
    }
