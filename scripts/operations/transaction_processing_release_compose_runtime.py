"""Local Compose runtime adapter for transaction release rehearsals.

This adapter is intentionally limited to one generated Compose project. It
never operates on the shared app-local project and it does not represent
cluster, UAT, or production certification.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol, Self, cast

import requests  # type: ignore[import-untyped]
from portfolio_common.config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from portfolio_common.db import create_sync_database_engine
from sqlalchemy import Engine, text

from scripts.operations.transaction_processing_cutover_offsets import (
    ConsumerGroupSnapshot,
    KafkaOffsetStore,
)
from scripts.operations.transaction_processing_load_support import (
    consumer_dlq_event_count,
    ingest_transactions,
    seed_load_context,
    transaction_processing_counts,
    wait_for_transaction_processing,
)
from scripts.operations.transaction_processing_release_evidence import (
    GOVERNED_RELEASE_RUNTIME_ENV_KEYS,
    FinancialEffectEvidence,
    ReleaseEvidenceError,
    ReleaseIdentity,
    assert_offsets_drained,
    assert_offsets_monotonic,
    validate_compose_project_name,
)
from scripts.operations.transaction_processing_release_rehearsal import CanaryResult

TRANSACTION_PROCESSING_GROUP = "portfolio_transaction_processing_group"
TRANSACTION_IMAGE_ENV = "LOTUS_PORTFOLIO_TRANSACTION_PROCESSING_IMAGE"
IMAGE_DIGEST_ENV = "LOTUS_IMAGE_DIGEST"
COMPOSE_SERVICE = "portfolio_transaction_processing_service"


class OffsetStore(Protocol):
    """Kafka offset operations required by the local rehearsal."""

    def snapshot(self, *, group_id: str, topic: str) -> ConsumerGroupSnapshot: ...

    def close(self) -> None: ...


class RuntimeEndpoints(Protocol):
    compose_project_name: str
    host_database_url: str
    kafka_bootstrap_servers: str
    e2e_ingestion_url: str
    e2e_transaction_processing_url: str


class PortReservation(Protocol):
    def release(self) -> None: ...


class PreparedRuntime(Protocol):
    values: dict[str, str]

    @property
    def port_reservation(self) -> PortReservation: ...

    @property
    def endpoints(self) -> RuntimeEndpoints: ...


class ManagedComposeRun(Protocol):
    compose_file: str

    @property
    def runtime(self) -> PreparedRuntime: ...

    def compose_command(self, *args: str) -> list[str]: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: None, exc: None, traceback: None) -> Literal[False]: ...


Runner = Callable[..., subprocess.CompletedProcess[Any]]
HttpGet = Callable[..., requests.Response]


def _create_release_database_engine(database_url: str) -> Engine:
    return create_sync_database_engine(
        runtime_identity="transaction-release-runtime", database_url=database_url
    )


@dataclass(frozen=True, slots=True)
class LocalComposeReleaseConfig:
    """Fixed, bounded configuration for one local release rehearsal."""

    receipt_id: str
    repo_root: Path
    transaction_topic: str = KAFKA_TRANSACTIONS_PERSISTED_TOPIC
    consumer_group: str = TRANSACTION_PROCESSING_GROUP
    ready_timeout_seconds: int = 240
    canary_timeout_seconds: int = 300
    canary_transaction_count: int = 20
    pull_images: bool = False

    def __post_init__(self) -> None:
        if self.ready_timeout_seconds < 1 or self.canary_timeout_seconds < 1:
            raise ReleaseEvidenceError("release rehearsal timeouts must be positive")
        if self.canary_transaction_count < 1 or self.canary_transaction_count > 100:
            raise ReleaseEvidenceError("release canary must contain between 1 and 100 transactions")


class LocalComposeReleaseRuntime:
    """Execute a release rehearsal inside one owned Compose project."""

    def __init__(
        self,
        *,
        managed_run: ManagedComposeRun,
        config: LocalComposeReleaseConfig,
        runner: Runner = subprocess.run,
        http_get: HttpGet = requests.get,
        engine_factory: Callable[[str], Engine] = _create_release_database_engine,
        offset_store_factory: Callable[[str, float], OffsetStore] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        project = managed_run.runtime.endpoints.compose_project_name
        validate_compose_project_name(project)
        self._managed_run = managed_run
        self._config = config
        self._runner = runner
        self._http_get = http_get
        self._engine_factory = engine_factory
        self._offset_store_factory = offset_store_factory or (
            lambda bootstrap_servers, timeout_seconds: KafkaOffsetStore(
                bootstrap_servers=bootstrap_servers,
                timeout_seconds=timeout_seconds,
            )
        )
        self._sleeper = sleeper
        self._project = project
        self._started = False
        self._cleaned = False
        self._engine: Engine | None = None
        self._offset_store: OffsetStore | None = None
        self._canary_sequence = 0

    def preflight(
        self,
        *,
        candidate: ReleaseIdentity,
        rollback: ReleaseIdentity,
    ) -> Mapping[str, Any]:
        """Verify both immutable images, pulling only when explicitly configured."""

        if candidate.digest_image_ref == rollback.digest_image_ref:
            raise ReleaseEvidenceError("candidate and rollback release digests must differ")
        return {
            "compose_project": self._project,
            "owned_resource_count_before_start": self._require_empty_project(),
            "candidate_image": self._verify_image(candidate),
            "rollback_image": self._verify_image(rollback),
        }

    def start_baseline(
        self,
        *,
        release: ReleaseIdentity,
    ) -> tuple[Mapping[str, Any], ConsumerGroupSnapshot]:
        """Start the rollback release, reconcile a canary, then quiesce its group."""

        if self._started:
            raise ReleaseEvidenceError("release rehearsal baseline is already running")
        self._set_release_image(release)
        self._managed_run.__enter__()
        self._started = True
        self._wait_for_migrations()
        self._initialize_connections()
        runtime_payload = self._runtime_payload(release)
        baseline_canary = self._run_fixed_canary(stage="baseline")
        baseline_findings = baseline_canary.effects.findings()
        if baseline_findings:
            raise ReleaseEvidenceError(
                "baseline financial effects failed: " + "; ".join(baseline_findings)
            )
        self._stop_transaction_service()
        offsets = self._wait_for_drained_offsets()
        return {
            **runtime_payload,
            "baseline_canary": {
                "effects": asdict(baseline_canary.effects),
                "profile": dict(baseline_canary.evidence),
            },
        }, offsets

    def handoff_offsets(
        self,
        *,
        baseline: ConsumerGroupSnapshot,
    ) -> ConsumerGroupSnapshot:
        """Prove stable-group offsets are unchanged while the worker is stopped."""

        current = self._snapshot_offsets()
        assert_offsets_monotonic(before=baseline, after=current)
        assert_offsets_drained(current)
        if current != baseline:
            raise ReleaseEvidenceError("stable consumer-group offsets changed during handoff")
        return current

    def deploy(self, *, release: ReleaseIdentity) -> Mapping[str, Any]:
        """Recreate only the transaction worker with the selected immutable image."""

        self._require_started()
        self._set_release_image(release)
        command = transaction_service_recreate_command(self._managed_run)
        self._run(command, env=self._managed_run.runtime.values)
        return self._runtime_payload(release)

    def run_canary(self, *, stage: str) -> CanaryResult:
        """Run the fixed transaction canary and capture offset/financial evidence."""

        self._require_started()
        if stage not in {"candidate", "rollback"}:
            raise ReleaseEvidenceError(f"unsupported release canary stage: {stage}")
        return self._run_fixed_canary(stage=stage)

    def quiesce(self, *, stage: str) -> ConsumerGroupSnapshot:
        """Stop only the transaction worker and prove its stable group is drained."""

        self._require_started()
        if stage not in {"candidate", "candidate_failure", "rollback"}:
            raise ReleaseEvidenceError(f"unsupported release quiesce stage: {stage}")
        self._stop_transaction_service()
        return self._wait_for_drained_offsets()

    def cleanup(self) -> int:
        """Close clients, tear down only the owned project, and count leftovers."""

        if self._cleaned:
            return owned_compose_resource_count(self._project, runner=self._runner)
        self._cleaned = True
        cleanup_errors: list[Exception] = []
        if self._offset_store is not None:
            try:
                self._offset_store.close()
            except Exception as exc:  # pragma: no cover - defensive client cleanup
                cleanup_errors.append(exc)
            self._offset_store = None
        if self._engine is not None:
            try:
                self._engine.dispose()
            except Exception as exc:  # pragma: no cover - defensive client cleanup
                cleanup_errors.append(exc)
            self._engine = None
        try:
            if self._started:
                self._managed_run.__exit__(None, None, None)
                self._started = False
            else:
                self._managed_run.runtime.port_reservation.release()
        except Exception as exc:
            cleanup_errors.append(exc)
        try:
            owned_count = owned_compose_resource_count(self._project, runner=self._runner)
        except Exception as exc:
            cleanup_errors.append(exc)
            owned_count = -1
        if cleanup_errors:
            primary = cleanup_errors[0]
            for secondary in cleanup_errors[1:]:
                primary.add_note(f"additional cleanup failure: {secondary}")
            raise ReleaseEvidenceError(f"release rehearsal cleanup failed: {primary}") from primary
        return owned_count

    def _require_empty_project(self) -> int:
        owned_count = owned_compose_resource_count(self._project, runner=self._runner)
        if owned_count:
            raise ReleaseEvidenceError(
                f"release rehearsal project already owns resources: {owned_count}"
            )
        return owned_count

    def _verify_image(self, release: ReleaseIdentity) -> Mapping[str, Any]:
        if self._config.pull_images:
            self._run(["docker", "pull", release.digest_image_ref])
        completed = self._run(
            [
                "docker",
                "image",
                "inspect",
                release.digest_image_ref,
                "--format",
                "{{json .RepoDigests}}",
            ]
        )
        repo_digests = _json_string_list(completed.stdout, label="image repository digests")
        if release.digest_image_ref not in repo_digests:
            raise ReleaseEvidenceError(
                f"pulled image does not expose the qualified release digest: "
                f"{release.digest_image_ref}"
            )
        return {
            "digest_image_ref": release.digest_image_ref,
            "repo_digests": repo_digests,
        }

    def _set_release_image(self, release: ReleaseIdentity) -> None:
        runtime_values = self._managed_run.runtime.values
        for key in GOVERNED_RELEASE_RUNTIME_ENV_KEYS:
            runtime_values[key] = release.runtime_env[key]
        runtime_values[IMAGE_DIGEST_ENV] = release.image_digest
        runtime_values[TRANSACTION_IMAGE_ENV] = release.digest_image_ref

    def _wait_for_migrations(self) -> None:
        from tests.test_support.docker_stack import wait_for_migration_runner

        wait_for_migration_runner(
            self._managed_run.compose_file,
            timeout_seconds=self._config.ready_timeout_seconds,
            runtime=self._managed_run.runtime,
        )

    def _initialize_connections(self) -> None:
        endpoints = self._managed_run.runtime.endpoints
        self._engine = self._engine_factory(endpoints.host_database_url)
        self._offset_store = self._offset_store_factory(
            endpoints.kafka_bootstrap_servers,
            float(self._config.ready_timeout_seconds),
        )

    def _runtime_payload(self, release: ReleaseIdentity) -> dict[str, Any]:
        endpoints = self._managed_run.runtime.endpoints
        ready = self._wait_for_ready(endpoints.e2e_transaction_processing_url)
        version = self._get_json(f"{endpoints.e2e_transaction_processing_url}/version")
        container = self._inspect_transaction_container(release)
        return {**version, "readiness": ready, "container": container}

    def _wait_for_ready(self, base_url: str) -> dict[str, Any]:
        deadline = time.monotonic() + self._config.ready_timeout_seconds
        last_error = "not attempted"
        while time.monotonic() < deadline:
            try:
                response = self._http_get(f"{base_url}/health/ready", timeout=5)
                if response.status_code == 200:
                    payload = response.json()
                    if isinstance(payload, dict):
                        return cast(dict[str, Any], payload)
                    last_error = "readiness payload is not an object"
                else:
                    last_error = f"status={response.status_code}"
            except (requests.RequestException, ValueError) as exc:
                last_error = str(exc)
            self._sleeper(1)
        raise ReleaseEvidenceError(f"transaction service did not become ready: {last_error}")

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self._http_get(url, timeout=10)
        if response.status_code != 200:
            raise ReleaseEvidenceError(f"runtime evidence endpoint failed: {url}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ReleaseEvidenceError(f"runtime evidence is not a JSON object: {url}")
        return cast(dict[str, Any], payload)

    def _inspect_transaction_container(self, release: ReleaseIdentity) -> dict[str, Any]:
        container_id = self._run(
            self._managed_run.compose_command("ps", "-q", COMPOSE_SERVICE),
            env=self._managed_run.runtime.values,
        ).stdout.strip()
        if not container_id:
            raise ReleaseEvidenceError("transaction service container is unavailable")
        payload = _json_object(
            self._run(["docker", "inspect", container_id, "--format", "{{json .}}"]).stdout,
            label="transaction container inspection",
        )
        config = payload.get("Config")
        if not isinstance(config, dict):
            raise ReleaseEvidenceError("transaction container config is unavailable")
        labels = config.get("Labels")
        if not isinstance(labels, dict):
            raise ReleaseEvidenceError("transaction container labels are unavailable")
        if labels.get("com.docker.compose.project") != self._project:
            raise ReleaseEvidenceError(
                "transaction container is not owned by the rehearsal project"
            )
        if labels.get("com.docker.compose.service") != COMPOSE_SERVICE:
            raise ReleaseEvidenceError("unexpected Compose service owns transaction container")
        if config.get("Image") != release.digest_image_ref:
            raise ReleaseEvidenceError("transaction container image differs from release digest")
        return {
            "container_id": container_id,
            "image_id": payload.get("Image"),
            "configured_image": config.get("Image"),
            "compose_project": self._project,
            "compose_service": COMPOSE_SERVICE,
        }

    def _run_fixed_canary(self, *, stage: str) -> CanaryResult:
        if self._engine is None:
            raise ReleaseEvidenceError("release canary database is not initialized")
        self._canary_sequence += 1
        run_suffix = uuid.uuid4().hex[:8].upper()
        portfolio_id = f"REL_{stage.upper()}_{run_suffix}"
        security_prefix = f"REL_{run_suffix}_SEC"
        seed_prefix = f"REL-{stage.upper()}-{run_suffix}"
        transaction_prefix = f"TX_{seed_prefix}"
        business_date = datetime.now(UTC).date().isoformat()
        endpoints = self._managed_run.runtime.endpoints
        baseline_dlq = self._consumer_dlq_count()
        seed_load_context(
            engine=self._engine,
            ingestion_base_url=endpoints.e2e_ingestion_url,
            run_id=f"{self._config.receipt_id}-{self._canary_sequence}",
            portfolio_id=portfolio_id,
            security_prefix=security_prefix,
            business_date=business_date,
            timeout_seconds=self._config.canary_timeout_seconds,
        )
        transaction_ids, _ = ingest_transactions(
            ingestion_base_url=endpoints.e2e_ingestion_url,
            portfolio_id=portfolio_id,
            batches=1,
            batch_size=self._config.canary_transaction_count,
            sleep_seconds_between_batches=0,
            seed_prefix=seed_prefix,
            security_prefix=security_prefix,
            transaction_date=f"{business_date}T09:00:00Z",
        )
        drain_seconds = wait_for_transaction_processing(
            engine=self._engine,
            portfolio_id=portfolio_id,
            transaction_id_prefix=transaction_prefix,
            expected=self._config.canary_transaction_count,
            expected_processing_claim_minimum=self._config.canary_transaction_count,
            timeout_seconds=self._config.canary_timeout_seconds,
        )
        if drain_seconds is None:
            raise ReleaseEvidenceError(f"{stage} release canary did not drain")
        outbox = self._wait_for_outbox_drain()
        counts = transaction_processing_counts(
            engine=self._engine,
            portfolio_id=portfolio_id,
            transaction_id_prefix=transaction_prefix,
        )
        operational = self._operational_counts(
            portfolio_id=portfolio_id,
            transaction_prefix=transaction_prefix,
        )
        readiness = self._wait_for_ready(endpoints.e2e_transaction_processing_url)
        current_dlq = self._consumer_dlq_count()
        if current_dlq < baseline_dlq:
            raise ReleaseEvidenceError("consumer DLQ evidence count moved backwards")
        unresolved_work = count_unresolved_canary_work(
            expected=self._config.canary_transaction_count,
            cost_count=counts.cost_count,
            cashflow_count=counts.cashflow_count,
            position_count=counts.position_count,
            processing_claim_count=counts.processing_claim_count,
        )
        effects = FinancialEffectEvidence(
            expected_transactions=self._config.canary_transaction_count,
            persisted_transactions=counts.transaction_count,
            expected_positions=self._config.canary_transaction_count,
            persisted_positions=counts.position_count,
            pending_outbox=outbox["pending_outbox"],
            failed_outbox=outbox["failed_outbox"],
            dlq_count=max(current_dlq - baseline_dlq, 0),
            duplicate_financial_effects=operational["duplicate_financial_effects"],
            reconciliation_findings=operational["reconciliation_findings"],
            unresolved_work=unresolved_work,
        )
        return CanaryResult(
            effects=effects,
            offsets=self._snapshot_offsets(),
            evidence={
                "profile": "fixed_transaction_release_canary_v1",
                "stage": stage,
                "portfolio_id": portfolio_id,
                "transaction_ids": transaction_ids,
                "drain_seconds": drain_seconds,
                "cost_count": counts.cost_count,
                "cashflow_count": counts.cashflow_count,
                "processing_claim_count": counts.processing_claim_count,
                "readiness": readiness,
                "consumer_dlq_count_before": baseline_dlq,
                "consumer_dlq_count_after": current_dlq,
            },
        )

    def _consumer_dlq_count(self) -> int:
        if self._engine is None:  # pragma: no cover - guarded by caller
            raise ReleaseEvidenceError("release canary database is not initialized")
        return consumer_dlq_event_count(
            engine=self._engine,
            consumer_group=self._config.consumer_group,
            original_topic=self._config.transaction_topic,
        )

    def _wait_for_outbox_drain(self) -> dict[str, int]:
        if self._engine is None:  # pragma: no cover - guarded by caller
            raise ReleaseEvidenceError("release canary database is not initialized")
        deadline = time.monotonic() + self._config.canary_timeout_seconds
        row: Mapping[str, Any] = {}
        while time.monotonic() < deadline:
            with self._engine.connect() as connection:
                row = (
                    connection.execute(
                        text(
                            """
                        SELECT
                          count(*) FILTER (WHERE status = 'PENDING') AS pending_outbox,
                          count(*) FILTER (WHERE status = 'FAILED') AS failed_outbox
                        FROM outbox_events
                        """
                        )
                    )
                    .mappings()
                    .one()
                )
            failed = int(row["failed_outbox"] or 0)
            pending = int(row["pending_outbox"] or 0)
            if failed:
                raise ReleaseEvidenceError(f"release canary produced failed outbox rows: {failed}")
            if pending == 0:
                return {"pending_outbox": pending, "failed_outbox": failed}
            self._sleeper(1)
        raise ReleaseEvidenceError(
            f"release canary outbox did not drain: pending={int(row.get('pending_outbox', 0))}"
        )

    def _operational_counts(
        self,
        *,
        portfolio_id: str,
        transaction_prefix: str,
    ) -> dict[str, int]:
        if self._engine is None:  # pragma: no cover - guarded by caller
            raise ReleaseEvidenceError("release canary database is not initialized")
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    WITH duplicate_effects AS (
                      SELECT coalesce(sum(effect_count - 1), 0) AS duplicate_count
                      FROM (
                        SELECT count(*) AS effect_count
                        FROM cashflows
                        WHERE transaction_id LIKE :transaction_pattern
                        GROUP BY transaction_id
                        HAVING count(*) > 1
                        UNION ALL
                        SELECT count(*) AS effect_count
                        FROM position_history
                        WHERE transaction_id LIKE :transaction_pattern
                        GROUP BY transaction_id
                        HAVING count(*) > 1
                      ) duplicates
                    )
                    SELECT
                      (SELECT duplicate_count FROM duplicate_effects)
                        AS duplicate_financial_effects,
                      (SELECT count(*)
                         FROM financial_reconciliation_findings
                        WHERE portfolio_id = :portfolio_id
                          AND resolved_at IS NULL) AS reconciliation_findings
                    """
                    ),
                    {
                        "portfolio_id": portfolio_id,
                        "transaction_pattern": f"{transaction_prefix}%",
                    },
                )
                .mappings()
                .one()
            )
        return {
            "duplicate_financial_effects": int(row["duplicate_financial_effects"] or 0),
            "reconciliation_findings": int(row["reconciliation_findings"] or 0),
        }

    def _stop_transaction_service(self) -> None:
        self._run(
            self._managed_run.compose_command("stop", COMPOSE_SERVICE),
            env=self._managed_run.runtime.values,
        )

    def _wait_for_drained_offsets(self) -> ConsumerGroupSnapshot:
        deadline = time.monotonic() + self._config.ready_timeout_seconds
        last_snapshot: ConsumerGroupSnapshot | None = None
        while time.monotonic() < deadline:
            last_snapshot = self._snapshot_offsets()
            try:
                assert_offsets_drained(last_snapshot)
                return last_snapshot
            except ReleaseEvidenceError:
                self._sleeper(1)
        raise ReleaseEvidenceError(
            f"transaction consumer group did not become inactive and drained: {last_snapshot}"
        )

    def _snapshot_offsets(self) -> ConsumerGroupSnapshot:
        if self._offset_store is None:
            raise ReleaseEvidenceError("release rehearsal offset store is not initialized")
        return self._offset_store.snapshot(
            group_id=self._config.consumer_group,
            topic=self._config.transaction_topic,
        )

    def _require_started(self) -> None:
        if not self._started:
            raise ReleaseEvidenceError("release rehearsal baseline has not started")

    def _run(
        self,
        command: list[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[Any]:
        return self._runner(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=dict(env) if env is not None else None,
        )


def transaction_service_recreate_command(managed_run: ManagedComposeRun) -> list[str]:
    """Return the only service-replacement command authorized by this adapter."""

    validate_compose_project_name(managed_run.runtime.endpoints.compose_project_name)
    return managed_run.compose_command(
        "up",
        "-d",
        "--no-deps",
        "--force-recreate",
        "--pull",
        "never",
        COMPOSE_SERVICE,
    )


def count_unresolved_canary_work(
    *,
    expected: int,
    cost_count: int,
    cashflow_count: int,
    position_count: int,
    processing_claim_count: int,
) -> int:
    """Count shortages or overproduction across exact canary side effects."""

    return sum(
        abs(actual - expected)
        for actual in (
            cost_count,
            cashflow_count,
            position_count,
            processing_claim_count,
        )
    )


def owned_compose_resource_count(project: str, *, runner: Runner = subprocess.run) -> int:
    """Count only resources carrying the exact generated project label."""

    validate_compose_project_name(project)
    label = f"label=com.docker.compose.project={project}"
    commands = (
        ["docker", "ps", "-aq", "--filter", label],
        ["docker", "network", "ls", "-q", "--filter", label],
        ["docker", "volume", "ls", "-q", "--filter", label],
    )
    resource_ids: set[str] = set()
    for command in commands:
        completed = runner(command, check=True, capture_output=True, text=True)
        resource_ids.update(line.strip() for line in completed.stdout.splitlines() if line.strip())
    return len(resource_ids)


def _json_object(raw: str, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReleaseEvidenceError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ReleaseEvidenceError(f"{label} must be a JSON object")
    return cast(dict[str, Any], payload)


def _json_string_list(raw: str, *, label: str) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReleaseEvidenceError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise ReleaseEvidenceError(f"{label} must be a JSON string list")
    return cast(list[str], payload)
