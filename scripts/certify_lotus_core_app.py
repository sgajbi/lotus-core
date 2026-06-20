from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "lotus-core-validation"
SUPPORTED_FEATURE_DOCS = (
    REPO_ROOT / "docs" / "supported-features.md",
    REPO_ROOT / "wiki" / "Supported-Features.md",
)
REQUIRED_SUPPORTED_FEATURE_TERMS = (
    "Portfolio and account source of record",
    "Transaction and booking evidence",
    "Position, valuation, and cashflow calculators",
    "Operational read plane",
    "Query control plane",
    "DPM source-data products",
    "Ingestion and replay",
    "Reconciliation and supportability",
    "Simulation and advisory source effects",
    "implementation-backed",
    "fail-closed",
)


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    ok: bool
    details: dict[str, Any]


def _check(name: str, ok: bool, details: dict[str, Any]) -> ValidationCheck:
    return ValidationCheck(name=name, ok=ok, details=details)


def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path = REPO_ROOT,
    skip: bool = False,
) -> ValidationCheck:
    if skip:
        return _check(name, True, {"skipped": True, "command": command})
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return _check(
        name,
        completed.returncode == 0,
        {
            "skipped": False,
            "command": command,
            "exit_code": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        },
    )


def _verify_supported_feature_truth() -> ValidationCheck:
    missing_files = [
        str(path.relative_to(REPO_ROOT)) for path in SUPPORTED_FEATURE_DOCS if not path.exists()
    ]
    missing_terms: dict[str, list[str]] = {}
    for path in SUPPORTED_FEATURE_DOCS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        absent = [term for term in REQUIRED_SUPPORTED_FEATURE_TERMS if term not in text]
        if absent:
            missing_terms[str(path.relative_to(REPO_ROOT))] = absent
    return _check(
        "supported_feature_truth",
        not missing_files and not missing_terms,
        {
            "checked_files": [str(path.relative_to(REPO_ROOT)) for path in SUPPORTED_FEATURE_DOCS],
            "missing_files": missing_files,
            "missing_terms": missing_terms,
            "required_terms": list(REQUIRED_SUPPORTED_FEATURE_TERMS),
        },
    )


def _static_contract_checks(args: argparse.Namespace) -> list[ValidationCheck]:
    commands = (
        ("openapi_contract", [sys.executable, "scripts/openapi_quality_gate.py"]),
        (
            "api_vocabulary_contract",
            [sys.executable, "scripts/api_vocabulary_inventory.py", "--validate-only"],
        ),
        ("route_family_contract", [sys.executable, "scripts/route_contract_family_guard.py"]),
        (
            "source_data_product_contract",
            [sys.executable, "scripts/source_data_product_contract_guard.py"],
        ),
        (
            "domain_product_contract",
            [sys.executable, "scripts/validate_domain_data_product_contracts.py"],
        ),
    )
    return [
        _run_command(name=name, command=command, skip=args.skip_static_contracts)
        for name, command in commands
    ]


def _runtime_smoke_check(args: argparse.Namespace) -> ValidationCheck:
    command = [
        sys.executable,
        "scripts/docker_endpoint_smoke.py",
        "--output-dir",
        str(args.output_dir),
    ]
    if args.runtime_build:
        command.append("--build")
    if args.runtime_skip_compose:
        command.append("--skip-compose")
    if args.runtime_reset_volumes:
        command.append("--reset-volumes")
    return _run_command(
        name="runtime_app_surface_smoke",
        command=command,
        skip=args.skip_runtime_smoke,
    )


def run_validation(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    checks: list[ValidationCheck] = [
        *_static_contract_checks(args),
        _verify_supported_feature_truth(),
        _runtime_smoke_check(args),
    ]
    failures = [asdict(check) for check in checks if not check.ok]
    return {
        "app": "lotus-core",
        "validation_scope": "app-level-supported-surface",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "passed" if not failures else "failed",
        "failed": len(failures),
        "checks": [asdict(check) for check in checks],
        "failures": failures,
        "runtime_surface_families": [
            "ingestion",
            "event-replay-and-ops",
            "operational-query-read-plane",
            "query-control-plane-support-and-lineage",
            "integration-policy-and-capabilities",
            "core-snapshot",
            "simulation",
            "source-data-contract-governance",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate lotus-core supported app surfaces with deterministic evidence."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--skip-static-contracts", action="store_true")
    parser.add_argument("--skip-runtime-smoke", action="store_true")
    parser.add_argument("--runtime-build", action="store_true")
    parser.add_argument("--runtime-skip-compose", action="store_true")
    parser.add_argument("--runtime-reset-volumes", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir = args.output_dir.resolve()
    evidence = run_validation(args)
    output_path = args.json_output or args.output_dir / "lotus-core-validation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print(f"Wrote: {output_path}")
    return 1 if evidence["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
