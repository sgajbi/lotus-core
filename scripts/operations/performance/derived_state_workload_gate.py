"""Run canonical derived-state workloads in an isolated managed Compose runtime."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Protocol, cast

from scripts.quality.ci_service_sets import DERIVED_STATE_WORKLOAD_GATE_SERVICES

if TYPE_CHECKING:
    from tests.test_support.managed_compose_run import ManagedComposeRun


class WorkloadConnectionEndpoints(Protocol):
    """Expose generated endpoints used by the managed bank-day subprocess."""

    compose_project_name: str
    host_database_url: str
    e2e_ingestion_url: str
    e2e_query_url: str
    e2e_query_control_plane_url: str
    e2e_event_replay_url: str
    e2e_financial_reconciliation_url: str


@dataclass(frozen=True, slots=True)
class DerivedStateWorkloadProfile:
    """Define one auditable workload shape and evidence posture."""

    name: str
    portfolio_count: int
    positions_per_portfolio: int
    transaction_batch_size: int
    sample_size: int
    drain_timeout_seconds: int
    certifying: bool

    @property
    def transaction_count(self) -> int:
        """Return the exact transaction and expected position count."""

        return self.portfolio_count * self.positions_per_portfolio


_CERTIFYING_PROFILES = {
    "daily": DerivedStateWorkloadProfile(
        name="derived-state-daily-volume",
        portfolio_count=1000,
        positions_per_portfolio=100,
        transaction_batch_size=2000,
        sample_size=5,
        drain_timeout_seconds=7200,
        certifying=True,
    ),
    "fan-in": DerivedStateWorkloadProfile(
        name="derived-state-aggregation-fan-in",
        portfolio_count=1,
        positions_per_portfolio=1000,
        transaction_batch_size=1000,
        sample_size=1,
        drain_timeout_seconds=3600,
        certifying=True,
    ),
}
_DIAGNOSTIC_SMOKE_PROFILE = DerivedStateWorkloadProfile(
    name="diagnostic-derived-state-workload-smoke",
    portfolio_count=2,
    positions_per_portfolio=5,
    transaction_batch_size=10,
    sample_size=2,
    drain_timeout_seconds=900,
    certifying=False,
)


def resolve_workload_profile(
    *,
    profile_name: str,
    diagnostic_smoke: bool,
) -> DerivedStateWorkloadProfile:
    """Resolve a canonical profile without allowing diagnostic evidence to certify capacity."""

    if diagnostic_smoke:
        return _DIAGNOSTIC_SMOKE_PROFILE
    try:
        return _CERTIFYING_PROFILES[profile_name]
    except KeyError as exc:
        supported = ", ".join(sorted(_CERTIFYING_PROFILES))
        raise ValueError(
            f"Unsupported workload profile {profile_name!r}; expected {supported}"
        ) from exc


def build_workload_environment(
    *,
    endpoints: WorkloadConnectionEndpoints,
    base_environment: Mapping[str, str],
) -> dict[str, str]:
    """Supply credential-bearing database configuration outside process arguments."""

    environment = dict(base_environment)
    environment["HOST_DATABASE_URL"] = endpoints.host_database_url
    return environment


def build_bank_day_command(
    *,
    python_executable: str,
    repo_root: Path,
    compose_file: Path,
    endpoints: WorkloadConnectionEndpoints,
    profile: DerivedStateWorkloadProfile,
    output_dir: str,
    resource_poll_interval_seconds: float,
    trade_date: str | None,
) -> list[str]:
    """Build the exact child command without placing database credentials in argv."""

    resolved_compose_file = (
        compose_file if compose_file.is_absolute() else repo_root / compose_file
    ).resolve()
    command = [
        python_executable,
        "-m",
        "scripts.operations.bank_day_load_scenario",
        "--compose-file",
        str(resolved_compose_file),
        "--compose-project-name",
        endpoints.compose_project_name,
        "--scenario-name",
        profile.name,
        "--portfolio-count",
        str(profile.portfolio_count),
        "--transactions-per-portfolio",
        str(profile.positions_per_portfolio),
        "--transaction-batch-size",
        str(profile.transaction_batch_size),
        "--sample-size",
        str(profile.sample_size),
        "--drain-timeout-seconds",
        str(profile.drain_timeout_seconds),
        "--resource-poll-interval-seconds",
        str(resource_poll_interval_seconds),
        "--derived-state-service",
        "portfolio_derived_state_service",
        "--ingestion-base-url",
        endpoints.e2e_ingestion_url,
        "--query-base-url",
        endpoints.e2e_query_url,
        "--query-control-base-url",
        endpoints.e2e_query_control_plane_url,
        "--event-replay-base-url",
        endpoints.e2e_event_replay_url,
        "--reconciliation-base-url",
        endpoints.e2e_financial_reconciliation_url,
        "--output-dir",
        output_dir,
    ]
    if trade_date is not None:
        command.extend(("--trade-date", trade_date))
    return command


def prepare_managed_run(*, args: argparse.Namespace, repo_root: Path) -> ManagedComposeRun:
    """Prepare one isolated full derived-state path for workload evidence."""

    from tests.test_support.managed_compose_run import prepare_managed_compose_run

    compose_file = Path(args.compose_file)
    if not compose_file.is_absolute():
        compose_file = repo_root / compose_file
    return prepare_managed_compose_run(
        profile="integration",
        scope=f"derived-state-{args.profile}-workload",
        compose_project_name=(
            args.compose_project_name
            or (os.getenv("COMPOSE_PROJECT_NAME") if args.skip_compose else None)
        ),
        compose_file=compose_file,
        services=DERIVED_STATE_WORKLOAD_GATE_SERVICES,
        build=args.build,
        log_path=repo_root
        / args.output_dir
        / "diagnostics"
        / f"derived-state-{args.profile}-workload-compose.log",
        endpoint_urls={
            "E2E_INGESTION_URL": args.ingestion_base_url,
            "E2E_QUERY_URL": args.query_base_url,
            "E2E_QUERY_CONTROL_PLANE_URL": args.query_control_base_url,
            "E2E_EVENT_REPLAY_URL": args.event_replay_base_url,
            "E2E_FINANCIAL_RECONCILIATION_URL": args.reconciliation_base_url,
            "HOST_DATABASE_URL": args.host_database_url,
        },
        allocate_dynamic_ports=not args.skip_compose,
        enable_demo_data_pack=False,
        keep_stack=args.keep_stack_up,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the managed workload CLI without starting external resources."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--compose-file", default="docker-compose.yml")
    parser.add_argument("--compose-project-name", default=None)
    parser.add_argument("--profile", choices=tuple(_CERTIFYING_PROFILES), default="daily")
    parser.add_argument("--diagnostic-smoke", action="store_true")
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--ingestion-base-url", default=None)
    parser.add_argument("--query-base-url", default=None)
    parser.add_argument("--query-control-base-url", default=None)
    parser.add_argument("--event-replay-base-url", default=None)
    parser.add_argument("--reconciliation-base-url", default=None)
    parser.add_argument("--host-database-url", default=None)
    parser.add_argument("--resource-poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--keep-stack-up", action="store_true")
    return parser


def main() -> int:
    """Start the managed runtime, execute one workload, and preserve diagnostics."""

    args = build_parser().parse_args()
    if args.resource_poll_interval_seconds <= 0:
        raise ValueError("resource_poll_interval_seconds must be positive")
    repo_root = Path(args.repo_root).resolve()
    profile = resolve_workload_profile(
        profile_name=args.profile,
        diagnostic_smoke=args.diagnostic_smoke,
    )
    managed_run = prepare_managed_run(args=args, repo_root=repo_root)
    managed_run.runtime.export_to(os.environ)
    endpoints = cast(WorkloadConnectionEndpoints, managed_run.runtime.endpoints)

    from tests.test_support.docker_stack import wait_for_migration_runner

    with ExitStack() as lifecycle:
        if not args.skip_compose:
            lifecycle.enter_context(managed_run)
            wait_for_migration_runner(
                managed_run.compose_file,
                timeout_seconds=300,
                runtime=managed_run.runtime,
            )
        else:
            managed_run.runtime.port_reservation.release()
        command = build_bank_day_command(
            python_executable=sys.executable,
            repo_root=repo_root,
            compose_file=Path(managed_run.compose_file),
            endpoints=endpoints,
            profile=profile,
            output_dir=args.output_dir,
            resource_poll_interval_seconds=args.resource_poll_interval_seconds,
            trade_date=args.trade_date,
        )
        environment = build_workload_environment(
            endpoints=endpoints,
            base_environment=os.environ,
        )
        completed = subprocess.run(
            command,
            cwd=repo_root,
            env=environment,
            check=False,
        )
        return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
