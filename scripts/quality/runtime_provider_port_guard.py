from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STANDARD_PATH = Path("docs/standards/runtime-provider-port-standard.md")
PROVIDER_PATH = Path("src/libs/portfolio-common/portfolio_common/runtime_providers.py")
REPRESENTATIVE_WORKFLOWS: dict[Path, tuple[str, ...]] = {
    Path("src/services/financial_reconciliation_service/app/services/reconciliation_service.py"): (
        "from portfolio_common.runtime_providers import",
        "_monotonic_timer.seconds()",
        "_id_generator.new_hex()",
    ),
    Path("src/services/query_service/app/services/core_snapshot_service.py"): (
        "from portfolio_common.runtime_providers import Clock, SystemClock",
        "_clock.utc_now()",
    ),
    Path("src/services/query_service/app/services/simulation_service.py"): (
        "from portfolio_common.runtime_providers import Clock, IdGenerator, "
        "SystemClock, UuidIdGenerator",
        "_clock.utc_now()",
        "_id_generator.new_id()",
    ),
}
PROVIDER_SNIPPETS = (
    "class Clock",
    "class MonotonicTimer",
    "class IdGenerator",
    "class SystemClock",
    "class SystemMonotonicTimer",
    "class UuidIdGenerator",
)
FORBIDDEN_RUNTIME_SNIPPETS = (
    "datetime.now(",
    "date.today(",
    "uuid4(",
    "perf_counter(",
)


@dataclass(frozen=True, slots=True)
class RuntimeProviderPortFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def _read_source(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def find_runtime_provider_port_findings(root: Path) -> list[RuntimeProviderPortFinding]:
    findings: list[RuntimeProviderPortFinding] = []
    if not (root / STANDARD_PATH).exists():
        findings.append(
            RuntimeProviderPortFinding(
                path=STANDARD_PATH.as_posix(),
                rule="missing-runtime-provider-standard",
                detail="runtime provider port standard is missing",
            )
        )

    provider_source = _read_source(root / PROVIDER_PATH)
    if provider_source is None:
        findings.append(
            RuntimeProviderPortFinding(
                path=PROVIDER_PATH.as_posix(),
                rule="missing-runtime-provider-module",
                detail="shared runtime provider port module is missing",
            )
        )
    else:
        for snippet in PROVIDER_SNIPPETS:
            if snippet not in provider_source:
                findings.append(
                    RuntimeProviderPortFinding(
                        path=PROVIDER_PATH.as_posix(),
                        rule="missing-runtime-provider-snippet",
                        detail=f"missing required snippet: {snippet}",
                    )
                )

    for relative_path, required_snippets in REPRESENTATIVE_WORKFLOWS.items():
        source = _read_source(root / relative_path)
        if source is None:
            findings.append(
                RuntimeProviderPortFinding(
                    path=relative_path.as_posix(),
                    rule="missing-provider-migrated-workflow",
                    detail="representative workflow is missing",
                )
            )
            continue
        for snippet in required_snippets:
            if snippet not in source:
                findings.append(
                    RuntimeProviderPortFinding(
                        path=relative_path.as_posix(),
                        rule="missing-runtime-provider-usage",
                        detail=f"missing required snippet: {snippet}",
                    )
                )
        for snippet in FORBIDDEN_RUNTIME_SNIPPETS:
            if snippet in source:
                findings.append(
                    RuntimeProviderPortFinding(
                        path=relative_path.as_posix(),
                        rule="direct-runtime-capability-call",
                        detail=f"direct runtime capability remains: {snippet}",
                    )
                )
    return findings


def main() -> int:
    findings = find_runtime_provider_port_findings(Path.cwd())
    if findings:
        print("Runtime provider port guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("Runtime provider port guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
