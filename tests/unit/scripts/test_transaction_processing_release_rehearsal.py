from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.operations.transaction_processing_cutover_offsets import (
    ConsumerGroupSnapshot,
    PartitionOffset,
)
from scripts.operations.transaction_processing_release_evidence import (
    COMPOSE_PROJECT_PREFIX,
    FinancialEffectEvidence,
    ReleaseIdentity,
    validate_release_pair,
)
from scripts.operations.transaction_processing_release_rehearsal import (
    CanaryResult,
    RehearsalContext,
    execute_release_rehearsal,
)
from scripts.release.write_image_release_manifest import build_release_manifest

CANDIDATE_SHA = "a" * 40
ROLLBACK_SHA = "b" * 40
CANDIDATE_DIGEST = "sha256:" + "c" * 64
ROLLBACK_DIGEST = "sha256:" + "d" * 64


def _manifest(*, sha: str, digest: str) -> dict[str, object]:
    image_ref = "ghcr.io/sgajbi/lotus-core/portfolio-transaction-processing-service"
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
        ci_pipeline_run_id="31366752006",
        sbom_generated=True,
        vulnerability_scan_status="passed",
        image_signed=True,
        provenance_attestation_generated=True,
        kubernetes_deploys_by_digest=True,
        promotion_environments=["dev", "uat", "prod"],
    )


def _releases() -> tuple[ReleaseIdentity, ReleaseIdentity]:
    return validate_release_pair(
        candidate_manifest=_manifest(sha=CANDIDATE_SHA, digest=CANDIDATE_DIGEST),
        rollback_manifest=_manifest(sha=ROLLBACK_SHA, digest=ROLLBACK_DIGEST),
    )


def _offsets(offset: int, *, active: int = 0) -> ConsumerGroupSnapshot:
    return ConsumerGroupSnapshot(
        group_id="portfolio_transaction_processing_group",
        active_member_count=active,
        partitions=(
            PartitionOffset(
                topic="transactions.persisted",
                partition=0,
                committed_offset=offset,
                high_watermark=offset,
            ),
        ),
    )


def _runtime_payload(release: ReleaseIdentity) -> dict[str, Any]:
    return {
        "service_name": release.service,
        "git_commit_sha": release.runtime_env["LOTUS_GIT_COMMIT_SHA"],
        "git_branch": release.runtime_env["LOTUS_GIT_BRANCH"],
        "build_timestamp": release.runtime_env["LOTUS_BUILD_TIMESTAMP"],
        "repo_url": release.runtime_env["LOTUS_REPO_URL"],
        "image_version": release.runtime_env["LOTUS_IMAGE_VERSION"],
        "image_digest": release.image_digest,
        "ci_pipeline_run_id": release.runtime_env["LOTUS_CI_RUN_ID"],
        "oci_labels": dict(release.oci_labels),
    }


def _effects() -> FinancialEffectEvidence:
    return FinancialEffectEvidence(
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


class FakeRuntime:
    def __init__(
        self,
        *,
        candidate: ReleaseIdentity,
        rollback: ReleaseIdentity,
        candidate_deploy_failure: Exception | None = None,
        candidate_failure: Exception | None = None,
        rollback_failure: Exception | None = None,
        cleanup_count: int = 0,
    ) -> None:
        self.candidate = candidate
        self.rollback = rollback
        self.candidate_deploy_failure = candidate_deploy_failure
        self.candidate_failure = candidate_failure
        self.rollback_failure = rollback_failure
        self.cleanup_count = cleanup_count
        self.calls: list[str] = []
        self.active_release = rollback

    def preflight(self, **_kwargs) -> dict[str, object]:
        self.calls.append("preflight")
        return {"docker_available": True}

    def start_baseline(self, *, release: ReleaseIdentity):
        self.calls.append("baseline")
        self.active_release = release
        return _runtime_payload(release), _offsets(10)

    def handoff_offsets(self, *, baseline: ConsumerGroupSnapshot):
        self.calls.append("handoff")
        return baseline

    def deploy(self, *, release: ReleaseIdentity):
        stage = "candidate" if release == self.candidate else "rollback"
        self.calls.append(f"deploy-{stage}")
        if stage == "candidate" and self.candidate_deploy_failure is not None:
            raise self.candidate_deploy_failure
        if stage == "rollback" and self.rollback_failure is not None:
            raise self.rollback_failure
        self.active_release = release
        return _runtime_payload(release)

    def run_canary(self, *, stage: str):
        self.calls.append(f"canary-{stage}")
        if stage == "candidate" and self.candidate_failure is not None:
            raise self.candidate_failure
        offset = 20 if stage == "candidate" else 30
        return CanaryResult(
            effects=_effects(),
            offsets=_offsets(offset, active=1),
            evidence={"profile": f"release-rehearsal-{stage}"},
        )

    def cleanup(self) -> int:
        self.calls.append("cleanup")
        return self.cleanup_count


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 10, 7, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


def _context() -> RehearsalContext:
    return RehearsalContext(
        receipt_id="release-rehearsal-20260810-070000",
        source_revision=CANDIDATE_SHA,
        source_tree_state="clean",
        compose_project=COMPOSE_PROJECT_PREFIX + "20260810-070000-a1b2c3d4",
    )


def test_release_rehearsal_executes_candidate_and_rollback_in_order() -> None:
    candidate, rollback = _releases()
    runtime = FakeRuntime(candidate=candidate, rollback=rollback)

    receipt = execute_release_rehearsal(
        runtime=runtime,
        context=_context(),
        candidate=candidate,
        rollback=rollback,
        clock=Clock(),
    )

    assert receipt["terminal_status"] == "passed"
    assert [phase["phase"] for phase in receipt["phases"]] == [
        "preflight",
        "baseline",
        "offset_handoff",
        "candidate_deploy",
        "canary",
        "rollback",
        "cleanup",
    ]
    assert runtime.calls == [
        "preflight",
        "baseline",
        "handoff",
        "deploy-candidate",
        "canary-candidate",
        "deploy-rollback",
        "canary-rollback",
        "cleanup",
    ]


def test_candidate_canary_failure_attempts_rollback_and_emits_failed_receipt() -> None:
    candidate, rollback = _releases()
    runtime = FakeRuntime(
        candidate=candidate,
        rollback=rollback,
        candidate_failure=RuntimeError("candidate canary failed"),
    )

    receipt = execute_release_rehearsal(
        runtime=runtime,
        context=_context(),
        candidate=candidate,
        rollback=rollback,
        clock=Clock(),
    )

    assert receipt["terminal_status"] == "failed"
    assert "deploy-rollback" in runtime.calls
    assert "canary-rollback" in runtime.calls
    assert runtime.calls[-1] == "cleanup"
    assert any("candidate canary failed" in failure for failure in receipt["failures"])


def test_partial_candidate_deploy_failure_still_attempts_rollback() -> None:
    candidate, rollback = _releases()
    runtime = FakeRuntime(
        candidate=candidate,
        rollback=rollback,
        candidate_deploy_failure=RuntimeError("candidate readiness failed after replacement"),
    )

    receipt = execute_release_rehearsal(
        runtime=runtime,
        context=_context(),
        candidate=candidate,
        rollback=rollback,
        clock=Clock(),
    )

    assert receipt["terminal_status"] == "failed"
    assert runtime.calls[-3:] == ["deploy-rollback", "canary-rollback", "cleanup"]
    assert any("candidate readiness failed" in item for item in receipt["failures"])


def test_rollback_failure_and_cleanup_residue_are_both_preserved() -> None:
    candidate, rollback = _releases()
    runtime = FakeRuntime(
        candidate=candidate,
        rollback=rollback,
        rollback_failure=RuntimeError("rollback image failed readiness"),
        cleanup_count=2,
    )

    receipt = execute_release_rehearsal(
        runtime=runtime,
        context=_context(),
        candidate=candidate,
        rollback=rollback,
        clock=Clock(),
    )

    assert receipt["terminal_status"] == "failed"
    assert any("rollback image failed readiness" in item for item in receipt["failures"])
    assert any("resources remain" in item for item in receipt["failures"])
    assert receipt["compose_ownership"]["owned_resource_count_after_cleanup"] is None


def test_financial_mismatch_triggers_rollback() -> None:
    candidate, rollback = _releases()
    runtime = FakeRuntime(candidate=candidate, rollback=rollback)
    original_canary = runtime.run_canary

    def mismatched_canary(*, stage: str):
        result = original_canary(stage=stage)
        if stage == "candidate":
            return CanaryResult(
                effects=FinancialEffectEvidence(
                    **{**asdict_effects(result.effects), "failed_outbox": 1}
                ),
                offsets=result.offsets,
                evidence=result.evidence,
            )
        return result

    runtime.run_canary = mismatched_canary  # type: ignore[method-assign]

    receipt = execute_release_rehearsal(
        runtime=runtime,
        context=_context(),
        candidate=candidate,
        rollback=rollback,
        clock=Clock(),
    )

    assert receipt["terminal_status"] == "failed"
    assert "deploy-rollback" in runtime.calls
    assert any("failed_outbox must be zero" in item for item in receipt["failures"])


def asdict_effects(effects: FinancialEffectEvidence) -> dict[str, int]:
    return {field_name: getattr(effects, field_name) for field_name in effects.__dataclass_fields__}
