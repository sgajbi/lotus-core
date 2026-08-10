"""Coordinate a fail-closed transaction-runtime release rehearsal."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, cast

from scripts.operations.transaction_processing_cutover_offsets import ConsumerGroupSnapshot
from scripts.operations.transaction_processing_release_evidence import (
    COMPOSE_PROJECT_PREFIX,
    REQUIRED_PHASE_ORDER,
    FinancialEffectEvidence,
    PhaseResult,
    RehearsalPhase,
    ReleaseEvidenceError,
    ReleaseIdentity,
    assert_offsets_drained,
    assert_offsets_monotonic,
    assert_runtime_matches_release,
    build_terminal_receipt,
    canonical_content_hash,
    redact_sensitive_values,
    validate_compose_project_name,
    validate_release_pair,
    validate_source_identity,
)

PLAN_SCHEMA = "lotus-core.transaction-processing-release-rehearsal-plan.v1"


@dataclass(frozen=True, slots=True)
class CanaryResult:
    """Financial and consumer-offset evidence from one fixed canary profile."""

    effects: FinancialEffectEvidence
    offsets: ConsumerGroupSnapshot
    evidence: Mapping[str, Any]


class ReleaseRehearsalRuntime(Protocol):
    """Infrastructure boundary required by the release rehearsal policy."""

    def preflight(
        self,
        *,
        candidate: ReleaseIdentity,
        rollback: ReleaseIdentity,
    ) -> Mapping[str, Any]: ...

    def start_baseline(
        self,
        *,
        release: ReleaseIdentity,
    ) -> tuple[Mapping[str, Any], ConsumerGroupSnapshot]: ...

    def handoff_offsets(
        self,
        *,
        baseline: ConsumerGroupSnapshot,
    ) -> ConsumerGroupSnapshot: ...

    def deploy(self, *, release: ReleaseIdentity) -> Mapping[str, Any]: ...

    def run_canary(self, *, stage: str) -> CanaryResult: ...

    def cleanup(self) -> int: ...


@dataclass(frozen=True, slots=True)
class RehearsalContext:
    """Immutable source and ownership identity for one rehearsal."""

    receipt_id: str
    source_revision: str
    source_tree_state: str
    compose_project: str


class _PhaseFailure(RuntimeError):
    def __init__(self, phase: RehearsalPhase, cause: Exception) -> None:
        super().__init__(str(cause))
        self.phase = phase
        self.cause = cause


def build_rehearsal_plan(
    *,
    context: RehearsalContext,
    candidate_manifest: Mapping[str, Any],
    rollback_manifest: Mapping[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    """Build a deterministic, non-mutating plan from qualified release evidence."""

    validate_compose_project_name(context.compose_project)
    validate_source_identity(
        source_revision=context.source_revision,
        source_tree_state=context.source_tree_state,
    )
    if context.source_tree_state != "clean":
        raise ReleaseEvidenceError("release rehearsal requires a clean source tree")
    candidate, rollback = validate_release_pair(
        candidate_manifest=candidate_manifest,
        rollback_manifest=rollback_manifest,
    )
    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "receipt_id": context.receipt_id,
        "generated_at": _timestamp(generated_at),
        "mode": "plan",
        "mutates_runtime": False,
        "cluster_certification": False,
        "source_revision": context.source_revision,
        "source_tree_state": context.source_tree_state,
        "compose_project": context.compose_project,
        "candidate_release": asdict(candidate),
        "rollback_release": asdict(rollback),
        "required_phases": [phase.value for phase in REQUIRED_PHASE_ORDER],
    }
    redacted = cast(dict[str, Any], redact_sensitive_values(plan))
    redacted["plan_content_hash"] = plan_content_hash(redacted)
    return redacted


def plan_content_hash(plan: Mapping[str, Any]) -> str:
    """Return the deterministic plan digest without its self-referential field."""

    return cast(
        str,
        canonical_content_hash(plan, excluded_fields={"plan_content_hash"}),
    )


def execute_release_rehearsal(
    *,
    runtime: ReleaseRehearsalRuntime,
    context: RehearsalContext,
    candidate: ReleaseIdentity,
    rollback: ReleaseIdentity,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Execute every controlled phase and return one terminal evidence receipt."""

    validate_compose_project_name(context.compose_project)
    started_at = _timestamp(clock())
    phases: list[PhaseResult] = []
    failures: list[str] = []
    invariants = {
        "release_digests_distinct": candidate.digest_image_ref != rollback.digest_image_ref,
        "compose_project_owned": True,
        "baseline_runtime_matches": False,
        "baseline_offsets_drained": False,
        "offset_handoff_verified": False,
        "candidate_runtime_matches": False,
        "candidate_canary_reconciled": False,
        "rollback_runtime_matches": False,
        "rollback_canary_reconciled": False,
        "offsets_monotonic": False,
        "cleanup_complete": False,
    }
    cleanup_owned_resource_count: int | None = None
    candidate_deployed = False
    baseline_offsets: ConsumerGroupSnapshot | None = None
    handoff_offsets: ConsumerGroupSnapshot | None = None
    candidate_offsets: ConsumerGroupSnapshot | None = None

    try:
        _run_phase(
            phases=phases,
            phase=RehearsalPhase.PREFLIGHT,
            clock=clock,
            operation=lambda: dict(runtime.preflight(candidate=candidate, rollback=rollback)),
        )

        def baseline_operation() -> Mapping[str, Any]:
            nonlocal baseline_offsets
            runtime_payload, baseline_offsets = runtime.start_baseline(release=rollback)
            assert_runtime_matches_release(release=rollback, runtime_payload=runtime_payload)
            assert_offsets_drained(baseline_offsets)
            invariants["baseline_runtime_matches"] = True
            invariants["baseline_offsets_drained"] = True
            return {
                "runtime": dict(runtime_payload),
                "offsets": asdict(baseline_offsets),
            }

        _run_phase(
            phases=phases,
            phase=RehearsalPhase.BASELINE,
            clock=clock,
            operation=baseline_operation,
        )
        if baseline_offsets is None:  # pragma: no cover - defensive type narrowing
            raise ReleaseEvidenceError("baseline offset evidence was not captured")

        def handoff_operation() -> Mapping[str, Any]:
            nonlocal handoff_offsets
            handoff_offsets = runtime.handoff_offsets(baseline=baseline_offsets)
            assert_offsets_monotonic(before=baseline_offsets, after=handoff_offsets)
            assert_offsets_drained(handoff_offsets)
            invariants["offset_handoff_verified"] = True
            return {"offsets": asdict(handoff_offsets)}

        _run_phase(
            phases=phases,
            phase=RehearsalPhase.OFFSET_HANDOFF,
            clock=clock,
            operation=handoff_operation,
        )
        if handoff_offsets is None:  # pragma: no cover - defensive type narrowing
            raise ReleaseEvidenceError("offset handoff evidence was not captured")

        def candidate_deploy_operation() -> Mapping[str, Any]:
            nonlocal candidate_deployed
            candidate_deployed = True
            runtime_payload = runtime.deploy(release=candidate)
            assert_runtime_matches_release(release=candidate, runtime_payload=runtime_payload)
            invariants["candidate_runtime_matches"] = True
            return {"runtime": dict(runtime_payload)}

        _run_phase(
            phases=phases,
            phase=RehearsalPhase.CANDIDATE_DEPLOY,
            clock=clock,
            operation=candidate_deploy_operation,
        )

        def candidate_canary_operation() -> Mapping[str, Any]:
            nonlocal candidate_offsets
            result = runtime.run_canary(stage="candidate")
            _raise_for_effect_findings(stage="candidate", effects=result.effects)
            assert_offsets_monotonic(before=handoff_offsets, after=result.offsets)
            candidate_offsets = result.offsets
            invariants["candidate_canary_reconciled"] = True
            return {
                "effects": asdict(result.effects),
                "offsets": asdict(result.offsets),
                "profile": dict(result.evidence),
            }

        _run_phase(
            phases=phases,
            phase=RehearsalPhase.CANARY,
            clock=clock,
            operation=candidate_canary_operation,
        )
        if candidate_offsets is None:  # pragma: no cover - defensive type narrowing
            raise ReleaseEvidenceError("candidate offset evidence was not captured")

        _run_rollback_phase(
            runtime=runtime,
            rollback=rollback,
            before_offsets=candidate_offsets,
            phases=phases,
            invariants=invariants,
            clock=clock,
        )
    except _PhaseFailure as failure:
        failures.append(f"{failure.phase.value}: {failure.cause}")
        if candidate_deployed and failure.phase not in {
            RehearsalPhase.ROLLBACK,
            RehearsalPhase.CLEANUP,
        }:
            rollback_before = candidate_offsets or handoff_offsets
            if rollback_before is not None:
                try:
                    _run_rollback_phase(
                        runtime=runtime,
                        rollback=rollback,
                        before_offsets=rollback_before,
                        phases=phases,
                        invariants=invariants,
                        clock=clock,
                    )
                except _PhaseFailure as rollback_failure:
                    failures.append(f"rollback: {rollback_failure.cause}")
    finally:
        try:
            cleanup_owned_resource_count = _run_cleanup_phase(
                runtime=runtime,
                phases=phases,
                clock=clock,
            )
            invariants["cleanup_complete"] = cleanup_owned_resource_count == 0
        except _PhaseFailure as cleanup_failure:
            failures.append(f"cleanup: {cleanup_failure.cause}")

    return cast(
        dict[str, Any],
        build_terminal_receipt(
            receipt_id=context.receipt_id,
            started_at=started_at,
            ended_at=_timestamp(clock()),
            source_revision=context.source_revision,
            source_tree_state=context.source_tree_state,
            compose_project=context.compose_project,
            candidate=candidate,
            rollback=rollback,
            phases=phases,
            invariants=invariants,
            failures=failures,
            cleanup_owned_resource_count=cleanup_owned_resource_count,
        ),
    )


def _run_rollback_phase(
    *,
    runtime: ReleaseRehearsalRuntime,
    rollback: ReleaseIdentity,
    before_offsets: ConsumerGroupSnapshot,
    phases: list[PhaseResult],
    invariants: dict[str, bool],
    clock: Callable[[], datetime],
) -> None:
    def operation() -> Mapping[str, Any]:
        runtime_payload = runtime.deploy(release=rollback)
        assert_runtime_matches_release(release=rollback, runtime_payload=runtime_payload)
        invariants["rollback_runtime_matches"] = True
        result = runtime.run_canary(stage="rollback")
        _raise_for_effect_findings(stage="rollback", effects=result.effects)
        assert_offsets_monotonic(before=before_offsets, after=result.offsets)
        invariants["rollback_canary_reconciled"] = True
        invariants["offsets_monotonic"] = True
        return {
            "runtime": dict(runtime_payload),
            "effects": asdict(result.effects),
            "offsets": asdict(result.offsets),
            "profile": dict(result.evidence),
        }

    _run_phase(
        phases=phases,
        phase=RehearsalPhase.ROLLBACK,
        clock=clock,
        operation=operation,
    )


def _run_cleanup_phase(
    *,
    runtime: ReleaseRehearsalRuntime,
    phases: list[PhaseResult],
    clock: Callable[[], datetime],
) -> int:
    remaining = -1

    def operation() -> Mapping[str, Any]:
        nonlocal remaining
        remaining = runtime.cleanup()
        if remaining != 0:
            raise ReleaseEvidenceError(f"owned Compose resources remain after cleanup: {remaining}")
        return {"owned_resource_count_after_cleanup": remaining}

    _run_phase(
        phases=phases,
        phase=RehearsalPhase.CLEANUP,
        clock=clock,
        operation=operation,
    )
    return remaining


def _run_phase(
    *,
    phases: list[PhaseResult],
    phase: RehearsalPhase,
    clock: Callable[[], datetime],
    operation: Callable[[], Mapping[str, Any]],
) -> None:
    started_at = _timestamp(clock())
    try:
        evidence = operation()
    except Exception as exc:
        phases.append(
            PhaseResult(
                phase=phase,
                status="failed",
                started_at=started_at,
                ended_at=_timestamp(clock()),
                evidence={"error": str(exc)},
            )
        )
        raise _PhaseFailure(phase, exc) from exc
    phases.append(
        PhaseResult(
            phase=phase,
            status="passed",
            started_at=started_at,
            ended_at=_timestamp(clock()),
            evidence=evidence,
        )
    )


def _raise_for_effect_findings(
    *,
    stage: str,
    effects: FinancialEffectEvidence,
) -> None:
    findings = effects.findings()
    if findings:
        raise ReleaseEvidenceError(f"{stage} financial effects failed: {'; '.join(findings)}")


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReleaseEvidenceError("rehearsal clock must return timezone-aware timestamps")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    """Build the planning and explicit local-execution CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-release-manifest", required=True, type=Path)
    parser.add_argument("--rollback-release-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo-root", default=Path("."), type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--pull-images", action="store_true")
    parser.add_argument("--compose-file", default=Path("docker-compose.yml"), type=Path)
    parser.add_argument("--ready-timeout-seconds", default=240, type=int)
    parser.add_argument("--canary-timeout-seconds", default=300, type=int)
    parser.add_argument("--canary-transaction-count", default=20, type=int)
    return parser


def main() -> int:
    """Write an immutable plan or explicitly execute its isolated local rehearsal."""

    parser = build_parser()
    args = parser.parse_args()
    if args.pull_images and not args.execute:
        parser.error("--pull-images requires --execute")
    repo_root = args.repo_root.resolve()
    now = datetime.now(UTC)
    run_identity = now.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    context = RehearsalContext(
        receipt_id=f"transaction-release-rehearsal-{run_identity}",
        source_revision=_git_output(repo_root, "rev-parse", "HEAD"),
        source_tree_state=("dirty" if _git_output(repo_root, "status", "--porcelain") else "clean"),
        compose_project=COMPOSE_PROJECT_PREFIX + run_identity,
    )
    candidate_manifest = _read_json_object(args.candidate_release_manifest)
    rollback_manifest = _read_json_object(args.rollback_release_manifest)
    if not args.execute:
        plan = build_rehearsal_plan(
            context=context,
            candidate_manifest=candidate_manifest,
            rollback_manifest=rollback_manifest,
            generated_at=now,
        )
        _write_json_atomic(args.output, plan)
        print(json.dumps(plan, separators=(",", ":")))
        return 0

    candidate, rollback = validate_release_pair(
        candidate_manifest=candidate_manifest,
        rollback_manifest=rollback_manifest,
    )
    _validate_execution_source(context=context, candidate=candidate)
    runtime = _prepare_local_compose_runtime(
        args=args,
        context=context,
        repo_root=repo_root,
    )
    receipt = execute_release_rehearsal(
        runtime=runtime,
        context=context,
        candidate=candidate,
        rollback=rollback,
    )
    _write_json_atomic(args.output, receipt)
    print(json.dumps(receipt, separators=(",", ":")))
    return 0 if receipt["terminal_status"] == "passed" else 1


def _validate_execution_source(
    *,
    context: RehearsalContext,
    candidate: ReleaseIdentity,
) -> None:
    validate_source_identity(
        source_revision=context.source_revision,
        source_tree_state=context.source_tree_state,
    )
    if context.source_tree_state != "clean":
        raise ReleaseEvidenceError("release rehearsal execution requires a clean source tree")
    if candidate.git_commit_sha != context.source_revision:
        raise ReleaseEvidenceError(
            "candidate release Git SHA must match the exact rehearsal source revision"
        )


def _prepare_local_compose_runtime(
    *,
    args: argparse.Namespace,
    context: RehearsalContext,
    repo_root: Path,
) -> ReleaseRehearsalRuntime:
    from scripts.operations.transaction_processing_release_compose_runtime import (
        LocalComposeReleaseConfig,
        LocalComposeReleaseRuntime,
    )
    from scripts.quality.ci_service_sets import FAILURE_RECOVERY_GATE_SERVICES
    from tests.test_support.managed_compose_run import prepare_managed_compose_run

    compose_file = args.compose_file
    if not compose_file.is_absolute():
        compose_file = repo_root / compose_file
    output_path = args.output.resolve()
    managed_run = prepare_managed_compose_run(
        profile="integration",
        scope="transaction-release-rehearsal",
        compose_project_name=context.compose_project,
        compose_file=compose_file,
        services=FAILURE_RECOVERY_GATE_SERVICES,
        build=False,
        log_path=output_path.with_suffix(".compose.log"),
        allocate_dynamic_ports=True,
        keep_stack=False,
        reset_volumes=False,
    )
    return cast(
        ReleaseRehearsalRuntime,
        LocalComposeReleaseRuntime(
            managed_run=managed_run,
            config=LocalComposeReleaseConfig(
                receipt_id=context.receipt_id,
                repo_root=repo_root,
                ready_timeout_seconds=args.ready_timeout_seconds,
                canary_timeout_seconds=args.canary_timeout_seconds,
                canary_transaction_count=args.canary_transaction_count,
                pull_images=args.pull_images,
            ),
        ),
    )


def _git_output(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReleaseEvidenceError(f"release manifest must be a JSON object: {path}")
    return cast(dict[str, Any], payload)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
