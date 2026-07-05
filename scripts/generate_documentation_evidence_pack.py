from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "documentation-evidence"
DEFAULT_API_VOCABULARY_ARTIFACT = "api-vocabulary-inventory.json"

DOCUMENTATION_SURFACES = (
    "README.md",
    "docs/architecture/README.md",
    "docs/architecture/CODEBASE-REVIEW-LEDGER.md",
    "docs/operations-runbook.md",
    "docs/supported-features.md",
    "wiki/Supported-Features.md",
    "wiki/Validation-and-CI.md",
    "wiki/Operations-Runbook.md",
    "wiki/API-Surface.md",
)

RUNBOOK_TERMS = (
    "operator-facing posture",
    "support APIs",
    "replay audit",
)

MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class DocumentationEvidenceCheck:
    name: str
    ok: bool
    details: dict[str, Any]


def _check(name: str, ok: bool, details: dict[str, Any]) -> DocumentationEvidenceCheck:
    return DocumentationEvidenceCheck(name=name, ok=ok, details=details)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _run_command(
    *,
    name: str,
    command: list[str],
    artifact_paths: tuple[Path, ...] = (),
) -> DocumentationEvidenceCheck:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
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
            "command": command,
            "exit_code": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
            "artifact_paths": [_relative(path) for path in artifact_paths],
        },
    )


def _markdown_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    links: list[str] = []
    for match in MARKDOWN_LINK_PATTERN.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        links.append(target.split("#", 1)[0].split(" ", 1)[0].strip("<>"))
    return links


def _validate_markdown_links(*, name: str, paths: tuple[Path, ...]) -> DocumentationEvidenceCheck:
    missing: list[str] = []
    checked: list[str] = []
    for path in paths:
        if not path.exists():
            missing.append(_relative(path))
            continue
        checked.append(_relative(path))
        for link in _markdown_links(path):
            candidate = (path.parent / link).resolve()
            wiki_candidate = candidate.with_suffix(".md") if path.parent.name == "wiki" else None
            if not candidate.exists() and not (
                wiki_candidate is not None and wiki_candidate.exists()
            ):
                missing.append(f"{_relative(path)} -> {link}")

    return _check(name, not missing, {"checked_files": checked, "missing": missing})


def _validate_supported_features() -> DocumentationEvidenceCheck:
    return _run_command(
        name="supported_features_manifest",
        command=[sys.executable, "scripts/supported_features_guard.py"],
        artifact_paths=(
            REPO_ROOT
            / "contracts"
            / "supported-features"
            / "lotus-core-supported-features.v1.json",
        ),
    )


def _validate_runbooks() -> DocumentationEvidenceCheck:
    missing_terms: dict[str, list[str]] = {}
    runbook_path = REPO_ROOT / "docs/operations-runbook.md"
    if not runbook_path.exists():
        missing_terms[_relative(runbook_path)] = ["missing file"]
    else:
        text = runbook_path.read_text(encoding="utf-8")
        absent = [term for term in RUNBOOK_TERMS if term not in text]
        if absent:
            missing_terms[_relative(runbook_path)] = absent

    link_check = _validate_markdown_links(
        name="runbook_link_validation",
        paths=(
            REPO_ROOT / "docs/operations-runbook.md",
            REPO_ROOT / "wiki/Operations-Runbook.md",
        ),
    )
    incident_playbook_check = _run_command(
        name="incident_playbook_guard",
        command=[sys.executable, "scripts/incident_playbook_guard.py"],
        artifact_paths=(REPO_ROOT / "contracts" / "operations" / "incident-playbooks.v1.json",),
    )
    ok = not missing_terms and link_check.ok and incident_playbook_check.ok
    return _check(
        "runbook_validation",
        ok,
        {
            "required_terms": list(RUNBOOK_TERMS),
            "missing_terms": missing_terms,
            "link_validation": link_check.details,
            "incident_playbook_guard": incident_playbook_check.details,
        },
    )


def run_documentation_evidence(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    api_vocabulary_artifact = output_dir / DEFAULT_API_VOCABULARY_ARTIFACT
    manifest_path = args.json_output or output_dir / "documentation-evidence-pack.json"

    checks = [
        _validate_markdown_links(name="readme_link_validation", paths=(REPO_ROOT / "README.md",)),
        _run_command(
            name="wiki_link_validation",
            command=[sys.executable, "scripts/wiki_validation_guard.py"],
        ),
        _run_command(
            name="api_catalog_generation",
            command=[
                sys.executable,
                "scripts/api_vocabulary_inventory.py",
                "--output",
                str(api_vocabulary_artifact),
            ],
            artifact_paths=(api_vocabulary_artifact,),
        ),
        _run_command(
            name="rfc_ledger_check",
            command=[sys.executable, "scripts/rfc0083_closure_guard.py"],
        ),
        _validate_supported_features(),
        _validate_runbooks(),
    ]
    failures = [asdict(check) for check in checks if not check.ok]
    artifact_paths = [manifest_path, api_vocabulary_artifact]
    return {
        "app": "lotus-core",
        "evidence_scope": "documentation-release-evidence",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_sha": _git_sha(),
        "runtime_profile": args.runtime_profile,
        "command": args.invocation_command,
        "status": "passed" if not failures else "failed",
        "failed": len(failures),
        "artifact_paths": [_relative(path) for path in artifact_paths],
        "affected_documentation_surfaces": list(DOCUMENTATION_SURFACES),
        "checks": [asdict(check) for check in checks],
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a machine-readable lotus-core documentation evidence pack."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument(
        "--runtime-profile",
        default=os.environ.get("LOTUS_DOC_EVIDENCE_RUNTIME_PROFILE", "local-docs"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.invocation_command = " ".join([Path(sys.argv[0]).as_posix(), *sys.argv[1:]])
    evidence = run_documentation_evidence(args)
    output_path = args.json_output or args.output_dir.resolve() / "documentation-evidence-pack.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print(f"Wrote: {output_path}")
    return 1 if evidence["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
