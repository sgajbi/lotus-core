from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.validation import canonical_front_office_seed_proof as proof
from scripts.validation.canonical_front_office_seed_proof import (
    CommandResult,
    ProofConfig,
    ProofFailure,
    SeedExpectation,
)
from tools.front_office_seed_contract import load_front_office_seed_contract


def _expectation() -> SeedExpectation:
    return SeedExpectation(transactions=31, positions=11, valued_positions=11)


def _terminal_sql(**overrides: Any) -> dict[str, Any]:
    expectation = _expectation()
    value: dict[str, Any] = {
        "transactions": expectation.transactions,
        "current_positions": expectation.positions,
        "exact_date_snapshots": expectation.positions,
        "exact_date_valued_snapshots": expectation.valued_positions,
        "position_timeseries_latest_date": "2026-04-10",
        "portfolio_timeseries_latest_date": "2026-04-10",
        "valuation_jobs": {
            "pending": 0,
            "processing": 0,
            "failed": 0,
            "complete": 11,
            "attempt_min": 1,
            "attempt_max": 2,
        },
        "aggregation_jobs": {
            "pending": 0,
            "processing": 0,
            "failed": 0,
            "complete": 144,
            "attempt_min": 1,
            "attempt_max": 1,
        },
        "outbox": {"pending": 0, "failed": 0},
        "contention": {"active": 4, "lock_waiters": 2, "blocked": 1, "deadlocks": 0},
    }
    value.update(overrides)
    return value


def _terminal_api(**overrides: Any) -> dict[str, Any]:
    contract = load_front_office_seed_contract()
    expectation = _expectation()
    queue_fields = (
        "pending_valuation_jobs",
        "processing_valuation_jobs",
        "stale_processing_valuation_jobs",
        "failed_valuation_jobs",
        "pending_aggregation_jobs",
        "processing_aggregation_jobs",
        "stale_processing_aggregation_jobs",
        "failed_aggregation_jobs",
    )
    value: dict[str, Any] = {
        "positions": expectation.positions,
        "valued_positions": expectation.valued_positions,
        "transactions": expectation.transactions,
        "data_quality_status": "COMPLETE",
        "queues": dict.fromkeys(queue_fields, 0),
        "readiness": {
            "domain_statuses": {
                "holdings": "READY",
                "pricing": "READY",
                "transactions": "READY",
                "reporting": "READY",
            },
            "blocking_reason_count": 0,
            "total_positions": expectation.positions,
            "valued_positions": expectation.valued_positions,
            "unvalued_positions": 0,
        },
        "benchmark_id": contract.benchmark_id,
        "analytics_end_date": contract.canonical_as_of_date,
    }
    value.update(overrides)
    return value


def _config(tmp_path: Path, *, prebuild_images: bool = False) -> ProofConfig:
    contract = load_front_office_seed_contract()
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    return ProofConfig(
        compose_file=compose_file,
        output_dir=tmp_path / "output" / "task-runs",
        retained_project="lotus-core-app-local",
        scope="issue-799-fresh-canonical",
        portfolio_id=contract.portfolio_id,
        start_date=contract.seed_start_date,
        end_date=contract.canonical_as_of_date,
        benchmark_start_date=contract.benchmark_start_date,
        benchmark_id=contract.benchmark_id,
        wait_seconds=900,
        poll_interval_seconds=3,
        stable_observations=3,
        prebuild_images=prebuild_images,
        build_lock_path=tmp_path / "output" / "locks" / "image-build.lock",
        build_lock_wait_seconds=30,
    )


def test_psql_json_streams_sql_so_psql_expands_bound_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def run(command: tuple[str, ...], **kwargs: object) -> CommandResult:
        observed["command"] = command
        observed.update(kwargs)
        return CommandResult(command, 0, '{"portfolio_id":"P1"}\n', "")

    monkeypatch.setattr(proof, "_run", run)

    result = proof._psql_json(
        "postgres-container",
        "select :'portfolio_id';",
        variables={"portfolio_id": "P1"},
    )

    assert result == {"portfolio_id": "P1"}
    assert observed["command"] == (
        "docker",
        "exec",
        "-i",
        "postgres-container",
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "user",
        "-d",
        "portfolio_db",
        "-Atq",
        "--set",
        "portfolio_id=P1",
        "--file",
        "-",
    )
    assert observed["input_text"] == "select :'portfolio_id';"
    assert observed["timeout_seconds"] == 30


def test_fresh_database_query_keeps_temporary_table_for_streamed_session() -> None:
    assert "create temporary table proof_counts" in proof.FRESH_DATABASE_SQL
    assert "on commit drop" not in proof.FRESH_DATABASE_SQL.lower()


def test_fresh_database_accepts_only_governed_migration_rows() -> None:
    proof._assert_fresh_database(
        {
            "migration_seeded_rows": {
                "alembic_version": 1,
                "cashflow_rules": 25,
                "ingestion_ops_control": 1,
            },
            "unexpected_runtime_rows": {},
            "inspected_table_count": 72,
        }
    )


def test_run_converts_subprocess_timeout_to_bounded_proof_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*_args: Any, **_kwargs: Any) -> None:
        raise proof.subprocess.TimeoutExpired(["bounded-command"], timeout=7)

    monkeypatch.setattr(proof.subprocess, "run", timeout)

    with pytest.raises(ProofFailure, match="exceeded 7s"):
        proof._run(("bounded-command",), timeout_seconds=7)


def test_proof_evidence_names_are_unique_and_existing_files_are_never_overwritten(
    tmp_path: Path,
) -> None:
    first, second = proof._new_run_id(), proof._new_run_id()
    assert first != second
    evidence = tmp_path / "evidence.json"
    proof._write_new_text(evidence, "first")

    with pytest.raises(ProofFailure, match="Refusing to overwrite"):
        proof._write_new_text(evidence, "second")

    assert evidence.read_text(encoding="utf-8") == "first"


def test_canonical_config_rejects_weakened_observation_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof, "REPO_ROOT", tmp_path)
    config = _config(tmp_path, prebuild_images=True)
    monkeypatch.setattr(proof, "_common_git_lock_path", lambda: config.build_lock_path)

    with pytest.raises(ProofFailure, match="stable_observations"):
        proof._assert_canonical_config(
            replace(config, stable_observations=2),
            load_front_office_seed_contract(),
        )


def test_retained_container_identity_includes_restart_config_image_and_volume_mounts() -> None:
    identity = proof._retained_container_identity(
        {
            "Id": "container-id",
            "Name": "/retained-postgres",
            "Image": "sha256:image",
            "RestartCount": 2,
            "Config": {
                "Image": "postgres:17",
                "Labels": {
                    "com.docker.compose.service": "postgres",
                    "com.docker.compose.config-hash": "config-hash",
                },
            },
            "State": {
                "Status": "running",
                "Running": True,
                "Health": {"Status": "healthy"},
            },
            "NetworkSettings": {
                "Networks": {
                    "retained-network": {
                        "NetworkID": "network-id",
                        "EndpointID": "endpoint-id",
                        "Gateway": "172.20.0.1",
                        "IPAddress": "172.20.0.2",
                    }
                }
            },
            "Mounts": [
                {"Type": "bind", "Source": "ignored", "Destination": "/ignored"},
                {
                    "Type": "volume",
                    "Name": "retained-data",
                    "Destination": "/var/lib/postgresql/data",
                },
            ],
        }
    )

    assert identity == {
        "id": "container-id",
        "name": "/retained-postgres",
        "service": "postgres",
        "image_id": "sha256:image",
        "image_name": "postgres:17",
        "compose_config_hash": "config-hash",
        "restart_count": 2,
        "state": {"status": "running", "running": True, "health": "healthy"},
        "network_attachments": [
            {
                "network": "retained-network",
                "network_id": "network-id",
                "endpoint_id": "endpoint-id",
                "gateway": "172.20.0.1",
                "ip_address": "172.20.0.2",
            }
        ],
        "mounted_volumes": [{"name": "retained-data", "destination": "/var/lib/postgresql/data"}],
    }


def test_repository_provenance_rejects_credential_bearing_url() -> None:
    with pytest.raises(ProofFailure, match="credential-free"):
        proof._public_repository_url("https://token@github.com/sgajbi/lotus-core.git")


def test_prebuild_uses_explicit_cold_build_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: Any, **kwargs: Any) -> CommandResult:
        captured["command"] = tuple(command)
        captured.update(kwargs)
        return CommandResult(tuple(command), 0, "built", "")

    monkeypatch.setattr(proof, "_run", fake_run)
    config = _config(tmp_path, prebuild_images=True)
    proof._prebuild(
        config,
        {
            "commit_sha": "a" * 40,
            "branch": "feat/proof",
            "repository": "https://github.com/sgajbi/lotus-core",
        },
    )

    assert captured["timeout_seconds"] == proof.PREBUILD_TIMEOUT_SECONDS
    assert captured["command"][-2:] == (
        "--cache-dir",
        str(config.output_dir / "canonical-seed-buildx-cache"),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("poll_interval_seconds", 1),
        ("build_lock_path", Path("unshared-driver.lock")),
    ],
)
def test_canonical_config_rejects_timing_or_lock_weakening(
    field: str,
    value: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof, "REPO_ROOT", tmp_path)
    config = _config(tmp_path, prebuild_images=True)
    expected_lock = tmp_path / ".git" / "lotus-local-image-build.lock"
    monkeypatch.setattr(proof, "_common_git_lock_path", lambda: expected_lock)
    config = replace(config, build_lock_path=expected_lock)

    with pytest.raises(ProofFailure, match=field):
        proof._assert_canonical_config(
            replace(config, **{field: value}),
            load_front_office_seed_contract(),
        )


@pytest.mark.parametrize(
    "observation",
    [
        {
            "migration_seeded_rows": {"alembic_version": 1},
            "unexpected_runtime_rows": {"portfolios": 1},
            "inspected_table_count": 72,
        },
        {
            "migration_seeded_rows": {"unreviewed_bootstrap": 1},
            "unexpected_runtime_rows": {},
            "inspected_table_count": 72,
        },
        {
            "migration_seeded_rows": {},
            "unexpected_runtime_rows": {},
            "inspected_table_count": 0,
        },
    ],
)
def test_fresh_database_fails_closed(observation: dict[str, Any]) -> None:
    with pytest.raises(ProofFailure, match="not a fresh governed runtime"):
        proof._assert_fresh_database(observation)


def test_seed_command_is_ingest_only_without_cleanup_or_reprocessing(tmp_path: Path) -> None:
    endpoints = SimpleNamespace(
        e2e_ingestion_url="http://localhost:18100",
        e2e_query_url="http://localhost:18101",
        e2e_query_control_plane_url="http://localhost:18102",
    )
    managed = SimpleNamespace(runtime=SimpleNamespace(endpoints=endpoints))

    command = proof._seed_command(
        _config(tmp_path),
        managed,  # type: ignore[arg-type]
        "isolated-postgres",
    )

    assert command[:2] == (
        proof.sys.executable,
        "tools/front_office_portfolio_seed.py",
    )
    assert {"--skip-cleanup", "--force-ingest", "--ingest-only", "--skip-reprocess"} <= set(command)
    assert "--reprocess-after-ingest" not in command
    assert command[command.index("--postgres-container") + 1] == "isolated-postgres"
    assert command[command.index("--ingestion-base-url") + 1] == "http://localhost:18100"


def test_seed_environment_fences_first_party_source_to_current_checkout(
    tmp_path: Path,
) -> None:
    foreign_checkout = tmp_path / "lotus-core-foreign"
    managed = SimpleNamespace(
        runtime=SimpleNamespace(
            values={
                "PYTHONPATH": str(foreign_checkout),
                "RUNTIME_SENTINEL": "preserved",
            }
        )
    )

    environment = proof._seed_environment(managed)  # type: ignore[arg-type]

    assert environment["RUNTIME_SENTINEL"] == "preserved"
    assert str(foreign_checkout) not in environment["PYTHONPATH"]
    assert environment["LOTUS_REPOSITORY_ROOT"] == str(proof.REPO_ROOT.resolve())
    origin = proof.require_current_first_party_origin(
        repo_root=proof.REPO_ROOT,
        pythonpath=environment["PYTHONPATH"],
    )
    assert origin.is_relative_to(proof.REPO_ROOT.resolve())


def test_seed_expectation_is_derived_from_exact_canonical_workload(tmp_path: Path) -> None:
    assert (
        proof._seed_expectation(
            _config(tmp_path),
            load_front_office_seed_contract(),
        )
        == _expectation()
    )


def test_blockers_require_complete_core_and_database_truth() -> None:
    contract = load_front_office_seed_contract()
    observation = {"sql": _terminal_sql(), "api": _terminal_api()}

    assert (
        proof._blockers(
            observation,
            _expectation(),
            contract,
            contract.canonical_as_of_date,
        )
        == []
    )

    sql = _terminal_sql(
        outbox={"pending": 1, "failed": 0},
        contention={"active": 4, "lock_waiters": 2, "blocked": 1, "deadlocks": 1},
    )
    api = _terminal_api(readiness={"domain_statuses": {}, "blocking_reason_count": 1})
    blockers = proof._blockers(
        {"sql": sql, "api": api},
        _expectation(),
        contract,
        contract.canonical_as_of_date,
    )

    assert any("sql.outbox" in blocker for blocker in blockers)
    assert "sql.contention.deadlocks=1" in blockers
    assert any("api.readiness" in blocker for blocker in blockers)


def test_blockers_reject_missing_counts_instead_of_coercing_to_zero() -> None:
    contract = load_front_office_seed_contract()
    sql = _terminal_sql()
    sql["valuation_jobs"] = None
    api = _terminal_api()
    api["queues"] = None

    blockers = proof._blockers(
        {"sql": sql, "api": api},
        _expectation(),
        contract,
        contract.canonical_as_of_date,
    )

    assert "sql.valuation_jobs=missing" in blockers
    assert "api.queues=None" in blockers


def test_api_observation_rejects_missing_readiness_blocking_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_fields = (
        "pending_valuation_jobs",
        "processing_valuation_jobs",
        "stale_processing_valuation_jobs",
        "failed_valuation_jobs",
        "pending_aggregation_jobs",
        "processing_aggregation_jobs",
        "stale_processing_aggregation_jobs",
        "failed_aggregation_jobs",
    )
    responses = iter(
        [
            {"positions": [], "data_quality_status": "COMPLETE"},
            {"total": 0},
            dict.fromkeys(queue_fields, 0),
            {
                "holdings": {"status": "READY"},
                "pricing": {"status": "READY"},
                "transactions": {"status": "READY"},
                "reporting": {"status": "READY"},
                "snapshot_valuation_total_positions": 0,
                "snapshot_valuation_valued_positions": 0,
                "snapshot_valuation_unvalued_positions": 0,
            },
            {"benchmark_id": "benchmark"},
            {"performance_end_date": "2026-04-10"},
        ]
    )
    monkeypatch.setattr(proof, "_request_json", lambda *_args, **_kwargs: next(responses))

    with pytest.raises(ProofFailure, match="blocking_reasons"):
        proof._api_observation("http://query", "http://control", "portfolio", "2026-04-10")


def test_stable_observations_ignore_transient_contention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = load_front_office_seed_contract()
    sql_observations = iter(
        [
            _terminal_sql(transactions=_expectation().transactions - 1),
            _terminal_sql(
                contention={"active": 3, "lock_waiters": 1, "blocked": 0, "deadlocks": 0}
            ),
            _terminal_sql(
                contention={"active": 5, "lock_waiters": 2, "blocked": 1, "deadlocks": 0}
            ),
            _terminal_sql(
                contention={"active": 4, "lock_waiters": 0, "blocked": 0, "deadlocks": 0}
            ),
        ]
    )
    monkeypatch.setattr(proof, "_psql_json", lambda *_args, **_kwargs: next(sql_observations))
    monkeypatch.setattr(proof, "_api_observation", lambda *_args: _terminal_api())
    monkeypatch.setattr(proof.time, "sleep", lambda _seconds: None)
    endpoints = SimpleNamespace(
        e2e_query_url="http://query",
        e2e_query_control_plane_url="http://control",
    )
    managed = SimpleNamespace(runtime=SimpleNamespace(endpoints=endpoints))

    observations, peaks = proof._stable_observations(
        managed,  # type: ignore[arg-type]
        "postgres",
        _config(tmp_path),
        contract,
        _expectation(),
    )

    assert len(observations) == 3
    assert peaks == {"active": 5, "lock_waiters": 2, "blocked": 1}


def test_log_scanner_is_case_insensitive_and_does_not_retain_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof, "REPO_ROOT", tmp_path)
    log_path = tmp_path / "output" / "compose.log"
    log_path.parent.mkdir()
    service_logs = (
        "postgres ERROR: DEADLOCK DETECTED\n"
        "worker valuation.scheduler.poll_loop_failed portfolio=sensitive-value\n"
    )
    log_path.write_text(
        "compose_logs_exit_code=0\n"
        f"service_log_bytes={len(service_logs.encode())}\n"
        "--- service logs ---\n"
        f"{service_logs}",
        encoding="utf-8",
    )

    scan = proof._scan_log(log_path)

    assert scan["clean"] is False
    assert scan["signature_matches"]["deadlock_detected"] == 1
    assert scan["signature_matches"]["valuation_poll_failed"] == 1
    assert "sensitive-value" not in str(scan)


@pytest.mark.parametrize(
    "metadata",
    [
        "",
        "compose_logs_exit_code=9\nservice_log_bytes=15\n--- service logs ---\nservice output\n",
        "compose_logs_exit_code=0\nservice_log_bytes=0\n--- service logs ---\nservice output\n",
        "compose_logs_exit_code=0\nservice_log_bytes=99\n--- service logs ---\nservice output\n",
    ],
)
def test_log_scanner_rejects_untrustworthy_capture_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata: str,
) -> None:
    monkeypatch.setattr(proof, "REPO_ROOT", tmp_path)
    log_path = tmp_path / "compose.log"
    log_path.write_text(f"{metadata}service output\n", encoding="utf-8")

    with pytest.raises(ProofFailure, match="capture"):
        proof._scan_log(log_path)


def test_source_provenance_requires_clean_signed_exact_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head, tree, main, main_tree = "a" * 40, "b" * 40, "c" * 40, "d" * 40
    monkeypatch.setattr(
        proof,
        "resolve_build_metadata",
        lambda: {
            "LOTUS_GIT_COMMIT_SHA": head,
            "LOTUS_GIT_BRANCH": "feat/proof",
            "LOTUS_REPO_URL": "https://github.com/sgajbi/lotus-core",
        },
    )
    results = {
        ("git", "rev-parse", "HEAD"): CommandResult((), 0, head, ""),
        ("git", "rev-parse", "HEAD^{tree}"): CommandResult((), 0, tree, ""),
        ("git", "rev-parse", "origin/main"): CommandResult((), 0, main, ""),
        ("git", "rev-parse", "origin/main^{tree}"): CommandResult((), 0, main_tree, ""),
        ("git", "branch", "--show-current"): CommandResult((), 0, "feat/proof", ""),
        ("git", "status", "--porcelain"): CommandResult((), 0, " M tracked.py", ""),
        ("git", "verify-commit", head): CommandResult((), 0, "Good signature", ""),
        (
            "git",
            "merge-base",
            "--is-ancestor",
            "origin/main",
            "HEAD",
        ): CommandResult((), 0, "", ""),
    }
    monkeypatch.setattr(proof, "_run", lambda command, **_kwargs: results[tuple(command)])

    with pytest.raises(ProofFailure, match="clean named branch"):
        proof._source_provenance()


def test_source_provenance_rejects_a_different_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head, tree = "a" * 40, "b" * 40
    monkeypatch.setattr(
        proof,
        "resolve_build_metadata",
        lambda: {
            "LOTUS_GIT_COMMIT_SHA": head,
            "LOTUS_GIT_BRANCH": "feat/proof",
            "LOTUS_REPO_URL": "https://github.com/other/lotus-core",
        },
    )
    results = {
        ("git", "rev-parse", "HEAD"): CommandResult((), 0, head, ""),
        ("git", "rev-parse", "HEAD^{tree}"): CommandResult((), 0, tree, ""),
        ("git", "rev-parse", "origin/main"): CommandResult((), 0, head, ""),
        ("git", "rev-parse", "origin/main^{tree}"): CommandResult((), 0, tree, ""),
        ("git", "branch", "--show-current"): CommandResult((), 0, "feat/proof", ""),
        ("git", "status", "--porcelain"): CommandResult((), 0, "", ""),
        ("git", "verify-commit", head): CommandResult((), 0, "Good signature", ""),
        (
            "git",
            "merge-base",
            "--is-ancestor",
            "origin/main",
            "HEAD",
        ): CommandResult((), 0, "", ""),
    }
    monkeypatch.setattr(proof, "_run", lambda command, **_kwargs: results[tuple(command)])

    with pytest.raises(ProofFailure, match="sgajbi/lotus-core"):
        proof._source_provenance()


def test_image_record_rejects_revision_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof, "REPO_ROOT", tmp_path)
    service = next(iter(proof.SERVICE_BUILDS))
    _image_tag, dockerfile = proof.SERVICE_BUILDS[service]
    dockerfile_path = tmp_path / dockerfile
    dockerfile_path.parent.mkdir(parents=True)
    dockerfile_path.write_text("FROM scratch\n", encoding="utf-8")
    expected = {
        "org.opencontainers.image.revision": "a" * 40,
        "org.opencontainers.image.ref.name": "feat/proof",
        "org.opencontainers.image.source": "https://github.com/sgajbi/lotus-core",
        "org.opencontainers.image.version": "a" * 40,
    }
    labels = {
        **expected,
        "org.opencontainers.image.revision": "unknown",
        "org.opencontainers.image.created": "2026-07-23T00:00:00Z",
    }

    with pytest.raises(ProofFailure, match="provenance is incomplete"):
        proof._image_record(service, {"Id": "sha256:image", "Config": {"Labels": labels}}, expected)


def test_container_validation_requires_exact_verified_image() -> None:
    project, service = "lotus-proof", "postgres"
    raw = {
        "Id": "container",
        "Name": f"/{project}-{service}-1",
        "Image": "sha256:wrong",
        "RestartCount": 0,
        "Config": {
            "Image": "postgres:17",
            "Labels": {
                "com.docker.compose.project": project,
                "com.docker.compose.service": service,
                "com.docker.compose.config-hash": "config-hash",
            },
        },
        "State": {
            "Status": "running",
            "ExitCode": 0,
            "OOMKilled": False,
            "Health": {"Status": "healthy"},
        },
    }

    with pytest.raises(ProofFailure, match="provenance-verified image"):
        proof._validate_container(
            raw,
            project=project,
            images={service: {"image_id": "sha256:expected"}},
        )


def test_container_validation_classifies_starting_health_as_not_ready() -> None:
    project, service = "lotus-proof", "portfolio_derived_state_service"
    raw = {
        "Id": "container",
        "Name": f"/{project}-{service}-1",
        "Image": "sha256:expected",
        "RestartCount": 0,
        "Config": {
            "Image": "lotus-core/portfolio-derived-state-service:local",
            "Labels": {
                "com.docker.compose.project": project,
                "com.docker.compose.service": service,
                "com.docker.compose.config-hash": "config-hash",
            },
        },
        "State": {
            "Status": "running",
            "ExitCode": 0,
            "OOMKilled": False,
            "Health": {"Status": "starting"},
        },
    }

    with pytest.raises(proof.RuntimeNotReady, match="health.*starting"):
        proof._validate_container(
            raw,
            project=project,
            images={service: {"image_id": "sha256:expected"}},
        )


def test_container_validation_rejects_unhealthy_runtime() -> None:
    project, service = "lotus-proof", "portfolio_derived_state_service"
    raw = {
        "Id": "container",
        "Name": f"/{project}-{service}-1",
        "Image": "sha256:expected",
        "RestartCount": 0,
        "Config": {
            "Image": "lotus-core/portfolio-derived-state-service:local",
            "Labels": {
                "com.docker.compose.project": project,
                "com.docker.compose.service": service,
                "com.docker.compose.config-hash": "config-hash",
            },
        },
        "State": {
            "Status": "running",
            "ExitCode": 0,
            "OOMKilled": False,
            "Health": {"Status": "unhealthy"},
        },
    }

    with pytest.raises(ProofFailure, match="health.*unhealthy") as failure:
        proof._validate_container(
            raw,
            project=project,
            images={service: {"image_id": "sha256:expected"}},
        )
    assert not isinstance(failure.value, proof.RuntimeNotReady)


def test_runtime_inspection_prioritizes_terminal_failure_over_transient_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = "lotus-proof"

    def container(service: str, health: str) -> dict[str, Any]:
        return {
            "Id": f"{service}-container",
            "Name": f"/{project}-{service}-1",
            "Image": f"sha256:{service}",
            "RestartCount": 0,
            "Config": {
                "Image": f"lotus-core/{service}:local",
                "Labels": {
                    "com.docker.compose.project": project,
                    "com.docker.compose.service": service,
                    "com.docker.compose.config-hash": "config-hash",
                },
            },
            "State": {
                "Status": "running",
                "ExitCode": 0,
                "OOMKilled": False,
                "Health": {"Status": health},
            },
        }

    starting = container("portfolio_derived_state_service", "starting")
    unhealthy = container("query_service", "unhealthy")
    resources = {
        "containers": ["starting-container", "unhealthy-container"],
        "networks": ["network"],
        "volumes": ["volume"],
    }
    managed = SimpleNamespace(
        runtime=SimpleNamespace(
            endpoints=SimpleNamespace(compose_project_name=project),
            values={},
        )
    )
    monkeypatch.setattr(
        proof,
        "_project_resources",
        lambda *_args, **_kwargs: resources,
    )
    monkeypatch.setattr(
        proof,
        "_docker_json",
        lambda *_args, **_kwargs: [starting, unhealthy],
    )

    with pytest.raises(ProofFailure, match="terminal.*query_service.*unhealthy") as failure:
        proof._inspect_runtime(managed, {})
    assert not isinstance(failure.value, proof.RuntimeNotReady)


def test_project_resource_commands_are_capped_by_startup_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeouts: list[float] = []

    def run(command: Any, *, timeout_seconds: float, **_kwargs: object) -> CommandResult:
        timeouts.append(timeout_seconds)
        return CommandResult(tuple(command), 0, "", "")

    monotonic_values = iter((10.0, 10.2, 10.4))
    monkeypatch.setattr(proof, "_run", run)
    monkeypatch.setattr(proof.time, "monotonic", lambda: next(monotonic_values))

    assert proof._project_resources("lotus-proof", deadline=11.0) == {
        "containers": [],
        "networks": [],
        "volumes": [],
    }
    assert timeouts == pytest.approx([1.0, 0.8, 0.6])


def test_wait_for_runtime_retries_only_transient_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = {"project": "lotus-proof"}
    inspections: list[int] = []

    def inspect(*_args: object, **_kwargs: object) -> dict[str, Any]:
        inspections.append(len(inspections) + 1)
        if len(inspections) == 1:
            raise proof.RuntimeNotReady("health is starting")
        return runtime

    monotonic_values = iter((10.0, 10.1, 10.2, 10.3, 10.4))
    monkeypatch.setattr(proof, "_inspect_runtime", inspect)
    monkeypatch.setattr(proof.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(proof.time, "sleep", lambda _seconds: None)

    result = proof._wait_for_runtime(
        SimpleNamespace(),
        {},
        timeout_seconds=30,
        poll_seconds=2,
    )

    assert result["startup_readiness"] == {
        "attempts": 2,
        "elapsed_seconds": 0.4,
        "timeout_seconds": 30,
        "poll_seconds": 2,
    }
    assert inspections == [1, 2]


def test_wait_for_runtime_reports_last_transient_state_at_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspections: list[int] = []

    def inspect(*_args: object, **_kwargs: object) -> dict[str, Any]:
        inspections.append(len(inspections) + 1)
        raise proof.RuntimeNotReady("portfolio_derived_state_service health is starting")

    monkeypatch.setattr(proof, "_inspect_runtime", inspect)
    monotonic_values = iter((10.0, 10.1, 10.5, 11.1))
    monkeypatch.setattr(proof.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(proof.time, "sleep", lambda _seconds: None)

    with pytest.raises(
        ProofFailure,
        match=("within 1s after 1 inspections.*portfolio_derived_state_service health is starting"),
    ):
        proof._wait_for_runtime(
            SimpleNamespace(),
            {},
            timeout_seconds=1,
            poll_seconds=1,
        )
    assert inspections == [1]


def test_build_lane_removes_only_its_own_claim(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with proof._build_lane(config, "a" * 40) as evidence:
        assert config.build_lock_path.is_file()
        assert evidence["source_commit"] == "a" * 40

    assert config.build_lock_path.is_file()


def test_build_lane_recovers_orphaned_owner_record(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.build_lock_path.parent.mkdir(parents=True)
    config.build_lock_path.write_text(
        '{"pid": 999999, "source_commit": "orphaned"}\n',
        encoding="utf-8",
    )

    with proof._build_lane(config, "b" * 40) as evidence:
        assert evidence["source_commit"] == "b" * 40
    assert (
        json.loads(config.build_lock_path.read_text(encoding="utf-8"))["token"] == evidence["token"]
    )


def test_build_lane_excludes_live_owner(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with proof._build_lane(config, "a" * 40):
        with pytest.raises(ProofFailure, match="Timed out waiting for image build lane"):
            with proof._build_lane(
                replace(config, build_lock_wait_seconds=0),
                "b" * 40,
            ):
                pytest.fail("a second live owner acquired the build lane")


def test_build_lane_simultaneous_first_acquisition_has_one_owner(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), build_lock_wait_seconds=0)
    barrier = threading.Barrier(2)
    owner_acquired = threading.Event()
    contender_blocked = threading.Event()
    release_owner = threading.Event()
    outcomes: list[str] = []

    def contend(source_commit: str) -> None:
        barrier.wait(timeout=5)
        try:
            with proof._build_lane(config, source_commit):
                outcomes.append(f"owner:{source_commit}")
                owner_acquired.set()
                release_owner.wait(timeout=5)
        except ProofFailure:
            outcomes.append(f"blocked:{source_commit}")
            contender_blocked.set()

    threads = [
        threading.Thread(target=contend, args=("a" * 40,)),
        threading.Thread(target=contend, args=("b" * 40,)),
    ]
    for thread in threads:
        thread.start()
    assert owner_acquired.wait(timeout=5)
    assert contender_blocked.wait(timeout=5)
    release_owner.set()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert len([outcome for outcome in outcomes if outcome.startswith("owner:")]) == 1
    assert len([outcome for outcome in outcomes if outcome.startswith("blocked:")]) == 1
    assert json.loads(config.build_lock_path.read_text(encoding="utf-8"))["token"]


def test_run_proof_uses_nonbuilding_isolated_runtime_and_proves_teardown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, prebuild_images=True)
    monkeypatch.setattr(proof, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(proof, "_common_git_lock_path", lambda: config.build_lock_path)
    source = {
        "repository": "https://github.com/sgajbi/lotus-core",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "branch": "feat/canonical-seed-proof-driver",
        "signature_verified": True,
        "signature_evidence_sha256": "c" * 64,
        "worktree_clean": True,
    }
    images = {"postgres": {"image_id": "sha256:postgres"}}
    monkeypatch.setattr(proof, "_source_provenance", lambda: source)
    monkeypatch.setattr(proof, "_prebuild", lambda *_args: {"requested": False})
    monkeypatch.setattr(proof, "_inspect_images", lambda _source: images)
    prepared: list[dict[str, Any]] = []
    project = "lotus-e2e-issue-799-fresh-canonical-abcd1234"

    class FakeManaged:
        def __init__(self) -> None:
            self.runtime = SimpleNamespace(
                endpoints=SimpleNamespace(
                    compose_project_name=project,
                    e2e_ingestion_url="http://localhost:18100",
                    e2e_query_url="http://localhost:18101",
                    e2e_query_control_plane_url="http://localhost:18102",
                ),
                values={"COMPOSE_PROJECT_NAME": project},
                port_reservation=SimpleNamespace(release=lambda: None),
            )

        def __enter__(self) -> FakeManaged:
            return self

        def __exit__(self, *_args: object) -> bool:
            log_path = Path(prepared[0]["log_path"])
            log_path.write_text(
                "compose_logs_exit_code=0\n"
                "service_log_bytes=31\n"
                "--- service logs ---\n"
                "all services completed cleanly\n",
                encoding="utf-8",
            )
            return False

    fake_managed = FakeManaged()

    def fake_prepare(**kwargs: Any) -> FakeManaged:
        prepared.append(kwargs)
        return fake_managed

    monkeypatch.setattr(proof, "prepare_managed_compose_run", fake_prepare)
    retained = {
        "project": config.retained_project,
        "resources": {
            "containers": ["retained-container"],
            "networks": ["retained-network"],
            "volumes": ["retained-volume"],
        },
        "identity_sha256": "retained-hash",
    }
    generated = {
        "project": project,
        "resources": {"containers": [], "networks": [], "volumes": []},
        "identity_sha256": "empty-hash",
    }
    monkeypatch.setattr(
        proof,
        "_project_identity",
        lambda selected: generated if selected == project else retained,
    )
    monkeypatch.setattr(proof, "_postgres_container", lambda _managed: "postgres-id")
    monkeypatch.setattr(
        proof,
        "_inspect_runtime",
        lambda *_args, **_kwargs: {"project": project},
    )
    fresh = {
        "migration_seeded_rows": {"alembic_version": 1},
        "unexpected_runtime_rows": {},
        "inspected_table_count": 72,
    }
    monkeypatch.setattr(proof, "_psql_json", lambda *_args, **_kwargs: fresh)
    seed_invocations: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    seed_environment = {
        "COMPOSE_PROJECT_NAME": project,
        "PYTHONPATH": "repository-fenced",
    }
    monkeypatch.setattr(proof, "_seed_environment", lambda _managed: seed_environment)

    def fake_run(command: Any, **kwargs: Any) -> CommandResult:
        seed_invocations.append((tuple(command), kwargs))
        return CommandResult(tuple(command), 0, "seeded", "")

    monkeypatch.setattr(proof, "_run", fake_run)
    monkeypatch.setattr(
        proof,
        "_stable_observations",
        lambda *_args: ([{"sql": _terminal_sql(), "api": _terminal_api()}] * 3, {}),
    )

    result = proof.run_proof(config)

    assert result["outcome"] == "passed"
    assert result["contention"]["during_seed"]["sample_count"] >= 1
    assert result["generated_project_after_teardown"]["resources"] == {
        "containers": [],
        "networks": [],
        "volumes": [],
    }
    seed_command, seed_kwargs = seed_invocations[0]
    assert seed_command[:2] == (
        proof.sys.executable,
        "tools/front_office_portfolio_seed.py",
    )
    assert seed_kwargs["environment"] is seed_environment
    assert seed_kwargs["timeout_seconds"] == config.wait_seconds + 300
    assert prepared[0] == {
        "profile": "e2e",
        "scope": config.scope,
        "compose_file": config.compose_file,
        "services": tuple(proof.E2E_SMOKE_SERVICES),
        "build": False,
        "log_path": prepared[0]["log_path"],
        "allocate_dynamic_ports": True,
        "enable_demo_data_pack": False,
        "keep_stack": False,
        "reset_volumes": False,
    }
    assert "--skip-reprocess" in seed_command
