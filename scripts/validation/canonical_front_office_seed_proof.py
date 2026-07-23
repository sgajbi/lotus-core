"""Generate isolated, provenance-bound evidence for the canonical Core seed.

The driver owns one generated Compose project through ``ManagedComposeRun``. It never mutates the
retained app-local project: that project's exact resources are compared before and after the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
for source_root in (REPO_ROOT, REPO_ROOT / "src" / "libs" / "portfolio-common"):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from scripts.quality.ci_service_sets import E2E_SMOKE_SERVICES  # noqa: E402
from scripts.release.prebuild_ci_images import (  # noqa: E402
    SERVICE_BUILDS,
    resolve_build_metadata,
)
from tests.test_support.managed_compose_run import (  # noqa: E402
    ManagedComposeRun,
    prepare_managed_compose_run,
)
from tools.front_office_portfolio_seed import (  # noqa: E402
    build_front_office_portfolio_bundle,
)
from tools.front_office_seed_contract import (  # noqa: E402
    FrontOfficeSeedContract,
    load_front_office_seed_contract,
)

SCHEMA_VERSION = "lotus-core.canonical-front-office-seed-proof.v1"
DEFAULT_RETAINED_PROJECT = "lotus-core-app-local"
DEFAULT_OUTPUT_DIR = Path("output/task-runs")
DEFAULT_COMMAND_TIMEOUT_SECONDS = 900
PREBUILD_TIMEOUT_SECONDS = 5400
MIN_STABLE_OBSERVATIONS = 3
ONE_SHOT_SERVICES = frozenset({"kafka-topic-creator", "migration-runner"})
MIGRATION_SEEDED_TABLES = (
    "alembic_version",
    "cashflow_rules",
    "ingestion_ops_control",
)
FORBIDDEN_LOG_PATTERNS = {
    "deadlock_detected": r"deadlock detected",
    "index_tuple_context": r"while inserting index tuple",
    "valuation_upsert_failed": r"failed to stage valuation job upserts",
    "valuation_poll_failed": r"valuation\.scheduler\.poll_loop_failed",
    "valuation_execution_error": r"valuation\.scheduler\.execution_error",
    "transaction_aborted": r"current transaction is aborted",
    "postgres_panic": r"\bpanic\b",
    "out_of_memory": r"\boom\b|out of memory",
    "killed": r"\bkilled\b",
    "exit_137": r"exit code 137|exited with code 137",
}

FRESH_DATABASE_SQL = """
create temporary table proof_counts(name text primary key, rows bigint not null) on commit drop;
do $proof$
declare item record; exact_count bigint;
begin
  for item in select schemaname, tablename from pg_tables where schemaname = 'public' loop
    execute format('select count(*) from %I.%I', item.schemaname, item.tablename)
      into exact_count;
    insert into proof_counts values (item.tablename, exact_count);
  end loop;
end $proof$;
select jsonb_build_object(
  'migration_seeded_rows', coalesce(
    (select jsonb_object_agg(name, rows) from proof_counts
     where name = any(array['alembic_version','cashflow_rules','ingestion_ops_control'])),
    '{}'::jsonb),
  'unexpected_runtime_rows', coalesce(
    (select jsonb_object_agg(name, rows) from proof_counts
     where rows > 0
       and name <> all(array['alembic_version','cashflow_rules','ingestion_ops_control'])),
    '{}'::jsonb),
  'inspected_table_count', (select count(*) from proof_counts)
)::text;
"""

TERMINAL_SQL = """
with
valuation as (
  select
    count(*) filter (where status='PENDING') pending,
    count(*) filter (where status='PROCESSING') processing,
    count(*) filter (where status='FAILED') failed,
    count(*) filter (where status='COMPLETE') complete,
    min(attempt_count) attempt_min, max(attempt_count) attempt_max
  from portfolio_valuation_jobs where portfolio_id=:'portfolio_id'
),
aggregation as (
  select
    count(*) filter (where status='PENDING') pending,
    count(*) filter (where status='PROCESSING') processing,
    count(*) filter (where status='FAILED') failed,
    count(*) filter (where status='COMPLETE') complete,
    min(attempt_count) attempt_min, max(attempt_count) attempt_max
  from portfolio_aggregation_jobs where portfolio_id=:'portfolio_id'
),
outbox as (
  select
    count(*) filter (where status='PENDING') pending,
    count(*) filter (where status='FAILED') failed
  from outbox_events
),
contention as (
  select
    (select count(*) from pg_stat_activity
     where datname=current_database() and state='active' and pid<>pg_backend_pid()) active,
    (select count(*) from pg_stat_activity
     where datname=current_database() and wait_event_type='Lock') lock_waiters,
    (select count(*) from pg_stat_activity
     where datname=current_database() and cardinality(pg_blocking_pids(pid))>0) blocked,
    (select deadlocks from pg_stat_database where datname=current_database()) deadlocks
)
select jsonb_build_object(
  'transactions', (select count(*) from transactions where portfolio_id=:'portfolio_id'),
  'current_positions', (select count(*) from position_state
    where portfolio_id=:'portfolio_id' and status='CURRENT'),
  'exact_date_snapshots', (select count(distinct security_id) from daily_position_snapshots
    where portfolio_id=:'portfolio_id' and date=:'as_of_date'::date),
  'exact_date_valued_snapshots', (select count(distinct security_id)
    from daily_position_snapshots where portfolio_id=:'portfolio_id'
    and date=:'as_of_date'::date and market_value is not null
    and valuation_status='VALUED_CURRENT'),
  'position_timeseries_latest_date', (select max(date)::text from position_timeseries
    where portfolio_id=:'portfolio_id'),
  'portfolio_timeseries_latest_date', (select max(date)::text from portfolio_timeseries
    where portfolio_id=:'portfolio_id'),
  'valuation_jobs', (select to_jsonb(valuation) from valuation),
  'aggregation_jobs', (select to_jsonb(aggregation) from aggregation),
  'outbox', (select to_jsonb(outbox) from outbox),
  'contention', (select to_jsonb(contention) from contention)
)::text;
"""

CONTENTION_SQL = """
select jsonb_build_object(
  'active', (select count(*) from pg_stat_activity
    where datname=current_database() and state='active' and pid<>pg_backend_pid()),
  'lock_waiters', (select count(*) from pg_stat_activity
    where datname=current_database() and wait_event_type='Lock'),
  'blocked', (select count(*) from pg_stat_activity
    where datname=current_database() and cardinality(pg_blocking_pids(pid))>0),
  'deadlocks', (select deadlocks from pg_stat_database where datname=current_database())
)::text;
"""


class ProofFailure(RuntimeError):
    """Evidence is missing, ambiguous, or violates a proof invariant."""


@dataclass(frozen=True, slots=True)
class ProofConfig:
    compose_file: Path
    output_dir: Path
    retained_project: str
    scope: str
    portfolio_id: str
    start_date: str
    end_date: str
    benchmark_start_date: str
    benchmark_id: str
    wait_seconds: int
    poll_interval_seconds: int
    stable_observations: int
    prebuild_images: bool
    build_lock_path: Path
    build_lock_wait_seconds: int


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class SeedExpectation:
    transactions: int
    positions: int
    valued_positions: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_run_id() -> str:
    return f"{_utc_now():%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:12]}"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_new_text(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(value)
    except FileExistsError as exc:
        raise ProofFailure(f"Refusing to overwrite existing proof evidence: {path}") from exc


def _digest(value: Any) -> str:
    return _sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _public_repository_url(value: str) -> str:
    ssh_match = re.fullmatch(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?", value)
    if ssh_match:
        return f"https://github.com/{ssh_match.group(1)}"
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ProofFailure("Repository provenance must be a credential-free GitHub HTTPS URL.")
    path = parsed.path.removesuffix(".git").rstrip("/")
    if len([part for part in path.split("/") if part]) != 2:
        raise ProofFailure("Repository provenance does not identify one GitHub repository.")
    return urlunsplit(("https", "github.com", path, "", ""))


def _run(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    check: bool = True,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=REPO_ROOT,
            env=dict(environment) if environment is not None else None,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProofFailure(
            f"Command exceeded {timeout_seconds}s: {' '.join(str(part) for part in command)}"
        ) from exc
    result = CommandResult(tuple(command), completed.returncode, completed.stdout, completed.stderr)
    if check and result.returncode:
        raise ProofFailure(
            f"Command exited {result.returncode}: {' '.join(result.command)}; "
            f"stderr={result.stderr.strip()[:1000]}"
        )
    return result


def _source_provenance() -> dict[str, Any]:
    metadata = resolve_build_metadata()
    head = _run(("git", "rev-parse", "HEAD")).stdout.strip()
    tree = _run(("git", "rev-parse", "HEAD^{tree}")).stdout.strip()
    main = _run(("git", "rev-parse", "origin/main")).stdout.strip()
    main_tree = _run(("git", "rev-parse", "origin/main^{tree}")).stdout.strip()
    branch = _run(("git", "branch", "--show-current")).stdout.strip()
    dirty = _run(("git", "status", "--porcelain")).stdout.strip()
    signature = _run(("git", "verify-commit", head), check=False)
    main_is_ancestor = _run(
        ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"),
        check=False,
    )
    identities = (head, tree, main, main_tree)
    if any(not re.fullmatch(r"[0-9a-f]{40}", value) for value in identities):
        raise ProofFailure("Exact source commit/tree identity is unavailable.")
    if dirty or not branch or signature.returncode:
        raise ProofFailure("Proof requires a clean named branch with a verified HEAD signature.")
    if main_is_ancestor.returncode:
        raise ProofFailure("Proof source must contain the current origin/main history.")
    if metadata["LOTUS_GIT_COMMIT_SHA"] != head or metadata["LOTUS_GIT_BRANCH"] != branch:
        raise ProofFailure("Resolved build metadata does not match the checked-out source.")
    repository_url = metadata["LOTUS_REPO_URL"]
    if not repository_url or repository_url == "unknown":
        raise ProofFailure("Repository URL provenance is unavailable.")
    repository_url = _public_repository_url(repository_url)
    if repository_url != "https://github.com/sgajbi/lotus-core":
        raise ProofFailure("Repository provenance does not identify sgajbi/lotus-core.")
    return {
        "repository": repository_url,
        "commit_sha": head,
        "tree_sha": tree,
        "branch": branch,
        "origin_main": {
            "commit_sha": main,
            "tree_sha": main_tree,
            "relation": "exact" if head == main else "ancestor_of_head",
        },
        "signature_verified": True,
        "signature_evidence_sha256": _sha256_bytes(
            f"{signature.stdout}\n{signature.stderr}".encode()
        ),
        "worktree_clean": True,
    }


@contextmanager
def _build_lane(config: ProofConfig, source_commit: str) -> Iterator[dict[str, Any]]:
    """Serialize mutation of shared ``lotus-core/*:local`` image tags."""

    path = config.build_lock_path
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    evidence = {
        "token": token,
        "pid": os.getpid(),
        "source_commit": source_commit,
        "repository_root": str(REPO_ROOT),
        "claimed_at_utc": _utc_now().isoformat(),
    }
    deadline = time.monotonic() + config.build_lock_wait_seconds
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                owner = path.read_text(encoding="utf-8", errors="replace")[:1000]
                raise ProofFailure(f"Timed out waiting for image build lane; owner={owner}")
            time.sleep(1)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(evidence, stream, sort_keys=True)
    try:
        yield evidence
    finally:
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("token") != token:
            raise ProofFailure("Image build-lane ownership changed while held; lock retained.")
        path.unlink()


def _prebuild(config: ProofConfig, source: Mapping[str, Any]) -> dict[str, Any]:
    if not config.prebuild_images:
        return {"requested": False, "group": "e2e-smoke"}
    cache_dir = config.output_dir / "canonical-seed-buildx-cache"
    environment = dict(os.environ)
    environment.update(
        {
            "LOTUS_GIT_COMMIT_SHA": str(source["commit_sha"]),
            "LOTUS_GIT_BRANCH": str(source["branch"]),
            "LOTUS_IMAGE_VERSION": str(source["commit_sha"]),
            "LOTUS_REPO_URL": str(source["repository"]),
        }
    )
    result = _run(
        (
            sys.executable,
            "scripts/release/prebuild_ci_images.py",
            "--group",
            "e2e-smoke",
            "--cache-dir",
            str(cache_dir),
        ),
        environment=environment,
        timeout_seconds=PREBUILD_TIMEOUT_SECONDS,
    )
    return {
        "requested": True,
        "group": "e2e-smoke",
        "cache_dir": str(cache_dir),
        "exit_code": result.returncode,
        "stdout_sha256": _sha256_bytes(result.stdout.encode()),
        "stderr_sha256": _sha256_bytes(result.stderr.encode()),
    }


def _docker_json(command: Sequence[str]) -> Any:
    output = _run(command).stdout.strip()
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ProofFailure(f"Docker returned malformed JSON: {' '.join(command)}") from exc


def _project_resources(project: str) -> dict[str, list[str]]:
    label = f"label=com.docker.compose.project={project}"
    commands = {
        "containers": ("docker", "ps", "-aq", "--filter", label),
        "networks": ("docker", "network", "ls", "-q", "--filter", label),
        "volumes": ("docker", "volume", "ls", "-q", "--filter", label),
    }
    return {
        name: sorted(line for line in _run(command).stdout.splitlines() if line)
        for name, command in commands.items()
    }


def _compose_labels(value: Mapping[str, Any]) -> dict[str, str]:
    labels = value.get("Labels") or {}
    return {
        str(key): str(item)
        for key, item in sorted(labels.items())
        if str(key).startswith("com.docker.compose.")
    }


def _inspect_resources(
    command: Sequence[str], identities: Sequence[str]
) -> list[Mapping[str, Any]]:
    if not identities:
        return []
    value = _docker_json((*command, *identities))
    if not isinstance(value, list) or len(value) != len(identities):
        raise ProofFailure(f"Docker resource inspection is ambiguous: {' '.join(command)}")
    if any(not isinstance(item, dict) for item in value):
        raise ProofFailure(f"Docker resource inspection returned a non-object: {' '.join(command)}")
    return value


def _retained_container_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    config = value.get("Config") or {}
    labels = config.get("Labels") or {}
    mounts = value.get("Mounts") or []
    state = value.get("State") or {}
    network_settings = (value.get("NetworkSettings") or {}).get("Networks") or {}
    return {
        "id": value.get("Id"),
        "name": value.get("Name"),
        "service": labels.get("com.docker.compose.service"),
        "image_id": value.get("Image"),
        "image_name": config.get("Image"),
        "compose_config_hash": labels.get("com.docker.compose.config-hash"),
        "restart_count": value.get("RestartCount"),
        "state": {
            "status": state.get("Status"),
            "running": state.get("Running"),
            "health": (state.get("Health") or {}).get("Status"),
        },
        "network_attachments": [
            {
                "network": name,
                "network_id": details.get("NetworkID"),
                "endpoint_id": details.get("EndpointID"),
                "gateway": details.get("Gateway"),
                "ip_address": details.get("IPAddress"),
            }
            for name, details in sorted(network_settings.items())
            if isinstance(details, dict)
        ],
        "mounted_volumes": sorted(
            (
                {
                    "name": mount.get("Name"),
                    "destination": mount.get("Destination"),
                }
                for mount in mounts
                if isinstance(mount, dict) and mount.get("Type") == "volume"
            ),
            key=lambda item: (str(item["name"]), str(item["destination"])),
        ),
    }


def _retained_network_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    containers = value.get("Containers") or {}
    return {
        "id": value.get("Id"),
        "name": value.get("Name"),
        "driver": value.get("Driver"),
        "internal": value.get("Internal"),
        "attachable": value.get("Attachable"),
        "labels": _compose_labels(value),
        "containers": [
            {
                "id": identity,
                "name": details.get("Name"),
                "endpoint_id": details.get("EndpointID"),
                "ipv4_address": details.get("IPv4Address"),
                "ipv6_address": details.get("IPv6Address"),
            }
            for identity, details in sorted(containers.items())
            if isinstance(details, dict)
        ],
    }


def _retained_volume_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": value.get("Name"),
        "driver": value.get("Driver"),
        "mountpoint": value.get("Mountpoint"),
        "labels": _compose_labels(value),
        "options": value.get("Options") or {},
    }


def _project_identity(project: str) -> dict[str, Any]:
    resources = _project_resources(project)
    containers = [
        _retained_container_identity(item)
        for item in _inspect_resources(("docker", "inspect"), resources["containers"])
    ]
    networks = [
        _retained_network_identity(item)
        for item in _inspect_resources(("docker", "network", "inspect"), resources["networks"])
    ]
    volumes = [
        _retained_volume_identity(item)
        for item in _inspect_resources(("docker", "volume", "inspect"), resources["volumes"])
    ]
    identity = {
        "resources": resources,
        "containers": sorted(containers, key=lambda item: str(item["id"])),
        "networks": sorted(networks, key=lambda item: str(item["id"])),
        "volumes": sorted(volumes, key=lambda item: str(item["name"])),
    }
    return {
        "project": project,
        **identity,
        "identity_sha256": _digest(identity),
    }


def _inspect_image_tag(
    image_tag: str,
    cache: dict[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    if image_tag in cache:
        return cache[image_tag]
    raw = _docker_json(("docker", "image", "inspect", image_tag))
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
        raise ProofFailure(f"Image identity is ambiguous: {image_tag}")
    cache[image_tag] = raw[0]
    return raw[0]


def _image_record(
    service: str,
    inspection: Mapping[str, Any],
    expected_labels: Mapping[str, Any],
) -> dict[str, Any]:
    image_tag, dockerfile = SERVICE_BUILDS[service]
    labels = (inspection.get("Config") or {}).get("Labels") or {}
    mismatches = {
        key: labels.get(key)
        for key, expected in expected_labels.items()
        if labels.get(key) != expected
    }
    created, image_id = labels.get("org.opencontainers.image.created"), inspection.get("Id")
    if mismatches or not created or created == "unknown" or not image_id:
        raise ProofFailure(
            f"Image provenance is incomplete for {service}: "
            f"mismatches={mismatches}, created={created!r}, image_id={image_id!r}"
        )
    return {
        "image_tag": image_tag,
        "image_id": image_id,
        "dockerfile": dockerfile,
        "dockerfile_sha256": _sha256_file(REPO_ROOT / dockerfile),
        "oci_labels": {
            key: value
            for key, value in sorted(labels.items())
            if key.startswith("org.opencontainers.image.")
        },
    }


def _inspect_images(source: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    expected_labels = {
        "org.opencontainers.image.revision": source["commit_sha"],
        "org.opencontainers.image.ref.name": source["branch"],
        "org.opencontainers.image.source": source["repository"],
        "org.opencontainers.image.version": source["commit_sha"],
    }
    records: dict[str, dict[str, Any]] = {}
    inspections: dict[str, Mapping[str, Any]] = {}
    for service in E2E_SMOKE_SERVICES:
        image_tag, _ = SERVICE_BUILDS[service]
        records[service] = _image_record(
            service,
            _inspect_image_tag(image_tag, inspections),
            expected_labels,
        )
    return records


def _container_state_is_valid(
    *,
    service: str,
    status: str,
    exit_code: int,
    health: Any,
    oom_killed: bool,
    restart_count: int,
) -> bool:
    expected_status = "exited" if service in ONE_SHOT_SERVICES else "running"
    return (
        status == expected_status
        and exit_code == 0
        and health in (None, "healthy")
        and not oom_killed
        and restart_count == 0
    )


def _container_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    config, state = raw.get("Config") or {}, raw.get("State") or {}
    labels = config.get("Labels") or {}
    return {
        "id": raw.get("Id"),
        "name": raw.get("Name"),
        "service": str(labels.get("com.docker.compose.service") or ""),
        "compose_project": labels.get("com.docker.compose.project"),
        "image_id": raw.get("Image"),
        "image_name": config.get("Image"),
        "compose_config_hash": str(labels.get("com.docker.compose.config-hash") or ""),
        "status": str(state.get("Status") or ""),
        "exit_code": int(state.get("ExitCode") or 0),
        "health": (state.get("Health") or {}).get("Status"),
        "oom_killed": bool(state.get("OOMKilled")),
        "restart_count": int(raw.get("RestartCount") or 0),
    }


def _validate_container(
    raw: Mapping[str, Any],
    *,
    project: str,
    images: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    record = _container_record(raw)
    service = record["service"]
    state_valid = _container_state_is_valid(
        service=service,
        status=record["status"],
        exit_code=record["exit_code"],
        health=record["health"],
        oom_killed=record["oom_killed"],
        restart_count=record["restart_count"],
    )
    if (
        not service
        or record["compose_project"] != project
        or not record["compose_config_hash"]
        or not state_valid
    ):
        raise ProofFailure(
            f"Container state/identity is invalid for service {service or 'missing'}."
        )
    expected_image = images.get(service)
    if expected_image is not None and record["image_id"] != expected_image["image_id"]:
        raise ProofFailure(f"Container {service} did not start the provenance-verified image.")
    record.pop("compose_project")
    return record


def _inspect_runtime(
    managed: ManagedComposeRun,
    images: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    project = managed.runtime.endpoints.compose_project_name
    resources = _project_resources(project)
    if not all(resources.values()):
        raise ProofFailure(f"Managed project {project} has incomplete resource identity.")
    raw = _docker_json(("docker", "inspect", *resources["containers"]))
    if not isinstance(raw, list) or len(raw) != len(resources["containers"]):
        raise ProofFailure(f"Managed project {project} container inspection is ambiguous.")
    containers = [_validate_container(item, project=project, images=images) for item in raw]
    services = {item["service"] for item in containers}
    missing = sorted(set(E2E_SMOKE_SERVICES) - services)
    if missing:
        raise ProofFailure(f"Managed runtime is missing E2E services: {missing}")
    ports = {
        key: value
        for key, value in sorted(managed.runtime.values.items())
        if key.startswith("LOTUS_") and key.endswith(("_HOST_PORT", "_EXTERNAL_PORT"))
    }
    return {
        "project": project,
        "dynamic_ports": ports,
        "resources": resources,
        "containers": sorted(containers, key=lambda item: item["service"]),
        "identity_sha256": _digest({"resources": resources, "containers": containers}),
    }


def _postgres_container(managed: ManagedComposeRun) -> str:
    result = _run(
        managed.compose_command("ps", "-q", "postgres"),
        environment=managed.runtime.values,
    )
    ids = [line for line in result.stdout.splitlines() if line]
    if len(ids) != 1:
        raise ProofFailure(f"Expected one managed PostgreSQL container; found {ids}.")
    return ids[0]


def _psql_json(
    container: str,
    sql: str,
    *,
    variables: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    command = [
        "docker",
        "exec",
        container,
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "user",
        "-d",
        "portfolio_db",
        "-Atq",
    ]
    for key, value in sorted((variables or {}).items()):
        command.extend(("--set", f"{key}={value}"))
    output = _run((*command, "-c", sql), timeout_seconds=30).stdout.strip()
    try:
        value = json.loads(output.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise ProofFailure("PostgreSQL evidence query returned malformed JSON.") from exc
    if not isinstance(value, dict):
        raise ProofFailure("PostgreSQL evidence query did not return an object.")
    return value


def _assert_fresh_database(value: Mapping[str, Any]) -> None:
    unexpected = value.get("unexpected_runtime_rows")
    baseline = value.get("migration_seeded_rows")
    inspected = value.get("inspected_table_count")
    if (
        not isinstance(unexpected, dict)
        or unexpected
        or not isinstance(baseline, dict)
        or set(baseline) - set(MIGRATION_SEEDED_TABLES)
        or not isinstance(inspected, int)
        or isinstance(inspected, bool)
        or inspected <= 0
    ):
        raise ProofFailure(f"Database is not a fresh governed runtime: {value}")


def _seed_expectation(
    config: ProofConfig,
    contract: FrontOfficeSeedContract,
) -> SeedExpectation:
    bundle = build_front_office_portfolio_bundle(
        portfolio_id=config.portfolio_id,
        start_date=date.fromisoformat(config.start_date),
        end_date=date.fromisoformat(config.end_date),
        benchmark_start_date=date.fromisoformat(config.benchmark_start_date),
        benchmark_id=config.benchmark_id,
    )
    rows = [
        row
        for row in bundle.get("transactions", [])
        if isinstance(row, dict) and row.get("portfolio_id") == config.portfolio_id
    ]
    securities = {row.get("security_id") for row in rows if isinstance(row.get("security_id"), str)}
    result = SeedExpectation(len(rows), len(securities), len(securities))
    if (
        result.transactions < contract.min_transactions
        or result.positions < contract.min_positions
        or result.valued_positions < contract.min_valued_positions
    ):
        raise ProofFailure(f"Canonical seed shape violates its contract: {result}")
    return result


def _assert_canonical_config(
    config: ProofConfig,
    contract: FrontOfficeSeedContract,
) -> None:
    expected = {
        "portfolio_id": contract.portfolio_id,
        "start_date": contract.seed_start_date,
        "end_date": contract.canonical_as_of_date,
        "benchmark_start_date": contract.benchmark_start_date,
        "benchmark_id": contract.benchmark_id,
        "retained_project": DEFAULT_RETAINED_PROJECT,
        "scope": "issue-799-fresh-canonical",
        "poll_interval_seconds": 3,
    }
    actual = {field: getattr(config, field) for field in expected}
    mismatches = {
        field: {"expected": expected_value, "actual": actual[field]}
        for field, expected_value in expected.items()
        if actual[field] != expected_value
    }
    canonical_compose = (REPO_ROOT / "docker-compose.yml").resolve()
    if config.compose_file != canonical_compose:
        mismatches["compose_file"] = {
            "expected": str(canonical_compose),
            "actual": str(config.compose_file),
        }
    if config.stable_observations < MIN_STABLE_OBSERVATIONS:
        mismatches["stable_observations"] = {
            "expected": f">={MIN_STABLE_OBSERVATIONS}",
            "actual": config.stable_observations,
        }
    if not config.prebuild_images:
        mismatches["prebuild_images"] = {"expected": True, "actual": False}
    expected_lock_path = _common_git_lock_path()
    if config.build_lock_path != expected_lock_path:
        mismatches["build_lock_path"] = {
            "expected": str(expected_lock_path),
            "actual": str(config.build_lock_path),
        }
    governed_output = (REPO_ROOT / DEFAULT_OUTPUT_DIR).resolve()
    if not config.output_dir.is_relative_to(governed_output):
        mismatches["output_dir"] = {
            "expected": f"within {governed_output}",
            "actual": str(config.output_dir),
        }
    if mismatches:
        raise ProofFailure(f"Canonical certification configuration was weakened: {mismatches}")


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.request(method, url, json=payload, timeout=20)
    if not 200 <= response.status_code < 300:
        raise ProofFailure(f"Core API {method} {url} returned HTTP {response.status_code}.")
    try:
        value = response.json()
    except ValueError as exc:
        raise ProofFailure(f"Core API {method} {url} returned malformed JSON.") from exc
    if not isinstance(value, dict):
        raise ProofFailure(f"Core API {method} {url} did not return an object.")
    return value


def _required_int(value: Mapping[str, Any], field: str) -> int:
    result = value.get(field)
    if not isinstance(result, int) or isinstance(result, bool):
        raise ProofFailure(f"Required integer field {field} is missing.")
    return result


def _api_observation(query: str, control: str, portfolio: str, as_of: str) -> dict[str, Any]:
    positions = _request_json("GET", f"{query}/portfolios/{portfolio}/positions?as_of_date={as_of}")
    transactions = _request_json(
        "GET", f"{query}/portfolios/{portfolio}/transactions?limit=300&include_projected=false"
    )
    support = _request_json("GET", f"{control}/support/portfolios/{portfolio}/overview")
    readiness = _request_json(
        "GET", f"{control}/support/portfolios/{portfolio}/readiness?as_of_date={as_of}"
    )
    benchmark = _request_json(
        "POST",
        f"{control}/integration/portfolios/{portfolio}/benchmark-assignment",
        {"as_of_date": as_of, "consumer_system": "lotus-performance"},
    )
    analytics = _request_json(
        "POST",
        f"{control}/integration/portfolios/{portfolio}/analytics/reference",
        {"as_of_date": as_of, "consumer_system": "lotus-performance"},
    )
    rows = positions.get("positions")
    if not isinstance(rows, list):
        raise ProofFailure("Core positions response is missing its positions list.")
    blocking_reasons = readiness.get("blocking_reasons")
    if not isinstance(blocking_reasons, list):
        raise ProofFailure("Core readiness response is missing its blocking_reasons list.")
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
    return {
        "positions": len(rows),
        "valued_positions": sum(
            isinstance(row, dict)
            and isinstance(row.get("valuation"), dict)
            and row["valuation"].get("market_value") is not None
            for row in rows
        ),
        "transactions": _required_int(transactions, "total"),
        "data_quality_status": positions.get("data_quality_status"),
        "queues": {field: _required_int(support, field) for field in queue_fields},
        "readiness": {
            "domain_statuses": {
                domain: (readiness.get(domain) or {}).get("status")
                for domain in ("holdings", "pricing", "transactions", "reporting")
            },
            "blocking_reason_count": len(blocking_reasons),
            "total_positions": _required_int(readiness, "snapshot_valuation_total_positions"),
            "valued_positions": _required_int(readiness, "snapshot_valuation_valued_positions"),
            "unvalued_positions": _required_int(readiness, "snapshot_valuation_unvalued_positions"),
        },
        "benchmark_id": benchmark.get("benchmark_id"),
        "analytics_end_date": analytics.get("performance_end_date"),
    }


def _date_current(value: Any, expected: str) -> bool:
    return isinstance(value, str) and date.fromisoformat(value) >= date.fromisoformat(expected)


def _minimum_blockers(
    prefix: str,
    values: Mapping[str, Any],
    minimums: Mapping[str, int],
) -> list[str]:
    return [
        f"{prefix}.{field}={values.get(field)!r}<{minimum}"
        for field, minimum in minimums.items()
        if not isinstance(values.get(field), int) or values[field] < minimum
    ]


def _job_blockers(name: str, values: Any) -> list[str]:
    if not isinstance(values, dict):
        return [f"sql.{name}=missing"]
    blockers = [
        f"sql.{name}.{field}={values.get(field)!r}"
        for field in ("pending", "processing", "failed")
        if values.get(field) != 0
    ]
    if not isinstance(values.get("complete"), int) or values["complete"] <= 0:
        blockers.append(f"sql.{name}.complete={values.get('complete')!r}")
    return blockers


def _readiness_is_complete(value: Any, expectation: SeedExpectation) -> bool:
    return (
        isinstance(value, dict)
        and set(value.get("domain_statuses", {}).values()) == {"READY"}
        and value.get("blocking_reason_count") == 0
        and value.get("total_positions", 0) >= expectation.positions
        and value.get("valued_positions", 0) >= expectation.valued_positions
        and value.get("unvalued_positions") == 0
    )


def _sql_blockers(
    sql: Mapping[str, Any],
    expectation: SeedExpectation,
    as_of: str,
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(
        _minimum_blockers(
            "sql",
            sql,
            {
                "transactions": expectation.transactions,
                "current_positions": expectation.positions,
                "exact_date_snapshots": expectation.positions,
                "exact_date_valued_snapshots": expectation.valued_positions,
            },
        )
    )
    for group in ("valuation_jobs", "aggregation_jobs"):
        blockers.extend(_job_blockers(group, sql.get(group)))
    outbox = sql.get("outbox")
    if not isinstance(outbox, dict) or outbox.get("pending") != 0 or outbox.get("failed") != 0:
        blockers.append(f"sql.outbox={outbox!r}")
    for field in ("position_timeseries_latest_date", "portfolio_timeseries_latest_date"):
        if not _date_current(sql.get(field), as_of):
            blockers.append(f"sql.{field}={sql.get(field)!r}")
    contention = sql.get("contention")
    if not isinstance(contention, dict) or contention.get("deadlocks") != 0:
        deadlocks = contention.get("deadlocks") if isinstance(contention, dict) else None
        blockers.append(f"sql.contention.deadlocks={deadlocks!r}")
    return blockers


def _api_blockers(
    api: Mapping[str, Any],
    expectation: SeedExpectation,
    contract: FrontOfficeSeedContract,
    as_of: str,
) -> list[str]:
    blockers = _minimum_blockers(
        "api",
        api,
        {
            "transactions": expectation.transactions,
            "positions": expectation.positions,
            "valued_positions": expectation.valued_positions,
        },
    )
    if api.get("data_quality_status") != "COMPLETE":
        blockers.append(f"api.data_quality_status={api.get('data_quality_status')!r}")
    queues = api.get("queues")
    if not isinstance(queues, dict) or any(value != 0 for value in queues.values()):
        blockers.append(f"api.queues={queues!r}")
    readiness = api.get("readiness")
    if not _readiness_is_complete(readiness, expectation):
        blockers.append(f"api.readiness={readiness!r}")
    if api.get("benchmark_id") != contract.benchmark_id:
        blockers.append(f"api.benchmark_id={api.get('benchmark_id')!r}")
    if not _date_current(api.get("analytics_end_date"), as_of):
        blockers.append(f"api.analytics_end_date={api.get('analytics_end_date')!r}")
    return blockers


def _blockers(
    observation: Mapping[str, Any],
    expectation: SeedExpectation,
    contract: FrontOfficeSeedContract,
    as_of: str,
) -> list[str]:
    return [
        *_sql_blockers(observation["sql"], expectation, as_of),
        *_api_blockers(observation["api"], expectation, contract, as_of),
    ]


def _stable_observations(
    managed: ManagedComposeRun,
    postgres: str,
    config: ProofConfig,
    contract: FrontOfficeSeedContract,
    expectation: SeedExpectation,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    deadline = time.monotonic() + config.wait_seconds
    accepted: list[dict[str, Any]] = []
    prior: dict[str, Any] | None = None
    last_blockers = ["no_observation"]
    peaks = {"active": 0, "lock_waiters": 0, "blocked": 0}
    while time.monotonic() < deadline:
        sql = _psql_json(
            postgres,
            TERMINAL_SQL,
            variables={"portfolio_id": config.portfolio_id, "as_of_date": config.end_date},
        )
        api = _api_observation(
            managed.runtime.endpoints.e2e_query_url,
            managed.runtime.endpoints.e2e_query_control_plane_url,
            config.portfolio_id,
            config.end_date,
        )
        projection = {"sql": {**sql, "contention": None}, "api": api}
        observation = {
            "observed_at_utc": _utc_now().isoformat(),
            "projection_sha256": _digest(projection),
            "sql": sql,
            "api": api,
        }
        contention = sql.get("contention") or {}
        for field in peaks:
            value = contention.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                peaks[field] = max(peaks[field], value)
        last_blockers = _blockers(observation, expectation, contract, config.end_date)
        accepted = (
            [*accepted, observation]
            if not last_blockers and projection == prior
            else [observation]
            if not last_blockers
            else []
        )
        prior = projection
        if len(accepted) >= config.stable_observations:
            return accepted, peaks
        time.sleep(config.poll_interval_seconds)
    raise ProofFailure(
        f"Terminal truth did not stabilize: blockers={last_blockers}, "
        f"stable={len(accepted)}/{config.stable_observations}"
    )


def _seed_with_contention_sampling(
    config: ProofConfig,
    managed: ManagedComposeRun,
    postgres: str,
) -> tuple[CommandResult, dict[str, Any]]:
    stop = threading.Event()
    samples: list[dict[str, Any]] = []
    sampling_errors: list[str] = []

    def sample() -> None:
        while not stop.is_set():
            try:
                values = _psql_json(postgres, CONTENTION_SQL)
                samples.append({"observed_at_utc": _utc_now().isoformat(), **values})
            except Exception as exc:  # pragma: no cover - defensive evidence capture
                sampling_errors.append(f"{type(exc).__name__}: {exc}")
            stop.wait(min(config.poll_interval_seconds, 3))

    sampler = threading.Thread(target=sample, name="canonical-seed-contention", daemon=True)
    sampler.start()
    try:
        result = _run(
            _seed_command(config, managed, postgres),
            environment=managed.runtime.values,
            check=False,
            timeout_seconds=config.wait_seconds + 300,
        )
    finally:
        stop.set()
        sampler.join(timeout=35)
    if sampler.is_alive():
        raise ProofFailure("Contention sampler did not stop within its bounded join timeout.")
    if not samples:
        raise ProofFailure(f"No during-seed contention samples were captured: {sampling_errors}")
    peaks = {
        field: max(
            (
                value
                for sample_values in samples
                if isinstance((value := sample_values.get(field)), int)
                and not isinstance(value, bool)
            ),
            default=0,
        )
        for field in ("active", "lock_waiters", "blocked", "deadlocks")
    }
    return result, {
        "interval_seconds": min(config.poll_interval_seconds, 3),
        "sample_count": len(samples),
        "peaks": peaks,
        "samples": samples,
        "sampling_errors": sampling_errors,
    }


def _seed_command(
    config: ProofConfig, managed: ManagedComposeRun, postgres: str
) -> tuple[str, ...]:
    endpoints = managed.runtime.endpoints
    return (
        sys.executable,
        "tools/front_office_portfolio_seed.py",
        "--portfolio-id",
        config.portfolio_id,
        "--start-date",
        config.start_date,
        "--end-date",
        config.end_date,
        "--benchmark-start-date",
        config.benchmark_start_date,
        "--benchmark-id",
        config.benchmark_id,
        "--ingestion-base-url",
        endpoints.e2e_ingestion_url,
        "--query-base-url",
        endpoints.e2e_query_url,
        "--query-control-plane-base-url",
        endpoints.e2e_query_control_plane_url,
        "--wait-seconds",
        str(config.wait_seconds),
        "--poll-interval-seconds",
        str(config.poll_interval_seconds),
        "--postgres-container",
        postgres,
        "--skip-cleanup",
        "--force-ingest",
        "--ingest-only",
        "--skip-reprocess",
    )


def _write_streams(config: ProofConfig, run_id: str, result: CommandResult) -> dict[str, Any]:
    paths = {
        "stdout": config.output_dir / f"{run_id}-canonical-seed.stdout.log",
        "stderr": config.output_dir / f"{run_id}-canonical-seed.stderr.log",
    }
    _write_new_text(paths["stdout"], result.stdout)
    _write_new_text(paths["stderr"], result.stderr)
    return {
        "exit_code": result.returncode,
        **{
            f"{name}_{field}": value
            for name, path in paths.items()
            for field, value in (
                ("path", str(path.relative_to(REPO_ROOT))),
                ("sha256", _sha256_file(path)),
            )
        },
    }


def _scan_log(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ProofFailure(f"Managed Compose log was not captured: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = {
        name: len(re.findall(pattern, text, re.IGNORECASE))
        for name, pattern in FORBIDDEN_LOG_PATTERNS.items()
    }
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
        "signature_matches": matches,
        "clean": not any(matches.values()),
    }


def _postconditions(
    generated: Mapping[str, Any],
    retained_before: Mapping[str, Any],
    retained_after: Mapping[str, Any],
    log: Mapping[str, Any],
) -> None:
    if any(generated["resources"].values()):
        raise ProofFailure(f"Generated project retained resources: {generated['resources']}")
    if retained_before["identity_sha256"] != retained_after["identity_sha256"]:
        raise ProofFailure("Retained app-local project identity changed during isolated proof.")
    if not log.get("clean"):
        raise ProofFailure(f"Runtime log contains forbidden signatures: {log['signature_matches']}")


def _execute_proof(
    config: ProofConfig,
    *,
    run_id: str,
    source: Mapping[str, Any],
    retained_before: Mapping[str, Any],
) -> dict[str, Any]:
    compose_log_path = config.output_dir / f"{run_id}-canonical-seed-compose.log"
    if compose_log_path.exists():
        raise ProofFailure(f"Refusing to overwrite existing proof evidence: {compose_log_path}")
    prebuild = _prebuild(config, source)
    images = _inspect_images(source)
    managed = prepare_managed_compose_run(
        profile="e2e",
        scope=config.scope,
        compose_file=config.compose_file,
        services=tuple(E2E_SMOKE_SERVICES),
        build=False,
        log_path=compose_log_path,
        allocate_dynamic_ports=True,
        enable_demo_data_pack=False,
        keep_stack=False,
        reset_volumes=False,
    )
    project = managed.runtime.endpoints.compose_project_name
    if project == config.retained_project:
        managed.runtime.port_reservation.release()
        raise ProofFailure("Generated project collides with the retained app-local project.")

    runtime = fresh = seed = expectation = None
    observations: list[dict[str, Any]] = []
    contention: dict[str, int] = {}
    errors: list[Exception] = []
    try:
        with managed:
            postgres = _postgres_container(managed)
            runtime = _inspect_runtime(managed, images)
            fresh = _psql_json(postgres, FRESH_DATABASE_SQL)
            _assert_fresh_database(fresh)
            result, seed_contention = _seed_with_contention_sampling(config, managed, postgres)
            seed = _write_streams(config, run_id, result)
            if result.returncode:
                raise ProofFailure(f"Canonical seed exited {result.returncode}.")
            contract = load_front_office_seed_contract()
            expectation = _seed_expectation(config, contract)
            observations, contention = _stable_observations(
                managed, postgres, config, contract, expectation
            )
            runtime = _inspect_runtime(managed, images)
    except Exception as exc:
        errors.append(exc)

    generated_after = _project_identity(project)
    retained_after = _project_identity(config.retained_project)
    try:
        log = _scan_log(compose_log_path)
        _postconditions(generated_after, retained_before, retained_after, log)
    except Exception as exc:
        errors.append(exc)
        log = {"path": str(compose_log_path.relative_to(REPO_ROOT)), "clean": False}

    source_after: Mapping[str, Any] | None = None
    try:
        source_after = _source_provenance()
        stable_source_fields = ("repository", "commit_sha", "tree_sha", "branch")
        if any(source_after[field] != source[field] for field in stable_source_fields):
            raise ProofFailure("Checked-out source identity changed during canonical proof.")
    except Exception as exc:
        errors.append(exc)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at_utc": _utc_now().isoformat(),
        "outcome": "failed" if errors else "passed",
        "environment_class": "local_isolated_runtime",
        "certification_boundary": (
            "Branch-qualified Core runtime proof; not deployment or production certification."
        ),
        "source": source,
        "source_after": source_after,
        "compose": {
            "file": str(config.compose_file.relative_to(REPO_ROOT)),
            "sha256": _sha256_file(config.compose_file),
            "project": project,
            "profile": "e2e",
            "scope": config.scope,
            "build": False,
            "dynamic_ports": True,
            "demo_data_pack_enabled": False,
            "services": list(E2E_SMOKE_SERVICES),
        },
        "prebuild": prebuild,
        "images": images,
        "retained_project_before": retained_before,
        "runtime": runtime,
        "fresh_database": fresh,
        "seed": seed,
        "expected_seed_shape": asdict(expectation) if expectation else None,
        "stable_terminal_observations": observations,
        "contention": {
            "during_seed": seed_contention if seed else None,
            "terminal_peaks": contention,
        },
        "runtime_log": log,
        "generated_project_after_teardown": generated_after,
        "retained_project_after": retained_after,
        "failure": (
            None
            if not errors
            else [{"type": type(exc).__name__, "message": str(exc)} for exc in errors]
        ),
    }
    artifact = config.output_dir / f"{run_id}-canonical-front-office-seed-proof.json"
    _write_new_text(artifact, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    artifact_evidence = {
        "path": str(artifact.relative_to(REPO_ROOT)),
        "sha256": _sha256_file(artifact),
    }
    payload["artifact"] = artifact_evidence
    if errors:
        raise ProofFailure(
            f"Canonical seed proof failed; artifact={artifact_evidence['path']}; "
            f"sha256={artifact_evidence['sha256']}; cause={errors[0]}"
        ) from errors[0]
    return payload


def _write_bootstrap_failure(
    config: ProofConfig,
    run_id: str,
    exc: Exception,
    *,
    source: Mapping[str, Any] | None,
    retained_before: Mapping[str, Any] | None,
) -> Path:
    artifact = config.output_dir / f"{run_id}-canonical-front-office-seed-proof.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at_utc": _utc_now().isoformat(),
        "outcome": "failed",
        "environment_class": "local_isolated_runtime",
        "certification_boundary": (
            "Branch-qualified Core runtime proof; not deployment or production certification."
        ),
        "source": source,
        "retained_project_before": retained_before,
        "failure": [{"type": type(exc).__name__, "message": str(exc)}],
        "phase": "bootstrap",
    }
    _write_new_text(artifact, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return artifact


def run_proof(config: ProofConfig) -> dict[str, Any]:
    run_id = _new_run_id()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    artifact = config.output_dir / f"{run_id}-canonical-front-office-seed-proof.json"
    source: Mapping[str, Any] | None = None
    retained_before: Mapping[str, Any] | None = None
    try:
        contract = load_front_office_seed_contract()
        _assert_canonical_config(config, contract)
        source = _source_provenance()
        with _build_lane(config, str(source["commit_sha"])):
            retained_before = _project_identity(config.retained_project)
            return _execute_proof(
                config,
                run_id=run_id,
                source=source,
                retained_before=retained_before,
            )
    except Exception as exc:
        artifact_already_existed = artifact.is_file()
        if not artifact_already_existed:
            artifact = _write_bootstrap_failure(
                config,
                run_id,
                exc,
                source=source,
                retained_before=retained_before,
            )
        if isinstance(exc, ProofFailure) and artifact_already_existed:
            raise
        raise ProofFailure(
            f"Canonical seed proof failed; artifact={artifact.relative_to(REPO_ROOT)}; "
            f"sha256={_sha256_file(artifact)}; cause={exc}"
        ) from exc


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _common_git_lock_path() -> Path:
    raw = _run(("git", "rev-parse", "--git-common-dir")).stdout.strip()
    if not raw:
        raise ProofFailure("Git common directory is unavailable for the shared image-build lock.")
    common = Path(raw)
    if not common.is_absolute():
        common = (REPO_ROOT / common).resolve()
    return common / "lotus-local-image-build.lock"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    contract = load_front_office_seed_contract()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, default=Path("docker-compose.yml"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--retained-project", default=DEFAULT_RETAINED_PROJECT)
    parser.add_argument("--scope", default="issue-799-fresh-canonical")
    parser.add_argument("--portfolio-id", default=contract.portfolio_id)
    parser.add_argument("--start-date", default=contract.seed_start_date)
    parser.add_argument("--end-date", default=contract.canonical_as_of_date)
    parser.add_argument("--benchmark-start-date", default=contract.benchmark_start_date)
    parser.add_argument("--benchmark-id", default=contract.benchmark_id)
    parser.add_argument("--wait-seconds", type=_positive_int, default=900)
    parser.add_argument("--poll-interval-seconds", type=_positive_int, default=3)
    parser.add_argument("--stable-observations", type=_positive_int, default=3)
    parser.add_argument(
        "--prebuild-images",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prebuild the exact-source e2e-smoke image set before proof.",
    )
    parser.add_argument(
        "--build-lock-path",
        type=Path,
        default=_common_git_lock_path(),
    )
    parser.add_argument("--build-lock-wait-seconds", type=_positive_int, default=900)
    return parser.parse_args(argv)


def _config(args: argparse.Namespace) -> ProofConfig:
    contract = load_front_office_seed_contract()
    for field in ("start_date", "end_date", "benchmark_start_date"):
        date.fromisoformat(str(getattr(args, field)))
    if args.portfolio_id != contract.portfolio_id or args.benchmark_id != contract.benchmark_id:
        raise ProofFailure("Canonical portfolio or benchmark identity was overridden.")
    compose = (REPO_ROOT / args.compose_file).resolve()
    if not compose.is_file():
        raise ProofFailure(f"Compose file does not exist: {compose}")
    config = ProofConfig(
        compose_file=compose,
        output_dir=(REPO_ROOT / args.output_dir).resolve(),
        retained_project=str(args.retained_project),
        scope=str(args.scope),
        portfolio_id=str(args.portfolio_id),
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        benchmark_start_date=str(args.benchmark_start_date),
        benchmark_id=str(args.benchmark_id),
        wait_seconds=int(args.wait_seconds),
        poll_interval_seconds=int(args.poll_interval_seconds),
        stable_observations=int(args.stable_observations),
        prebuild_images=bool(args.prebuild_images),
        build_lock_path=(REPO_ROOT / args.build_lock_path).resolve(),
        build_lock_wait_seconds=int(args.build_lock_wait_seconds),
    )
    _assert_canonical_config(config, contract)
    return config


def main(argv: Sequence[str] | None = None) -> int:
    try:
        payload = run_proof(_config(parse_args(argv)))
    except ProofFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"Canonical seed proof passed: {payload['artifact']['path']} "
        f"(sha256={payload['artifact']['sha256']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
