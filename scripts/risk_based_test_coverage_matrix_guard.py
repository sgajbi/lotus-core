"""Validate the risk-based test coverage matrix contract."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MATRIX_PATH = Path("docs/standards/risk-based-test-coverage-matrix.v1.json")
PYPROJECT_PATH = Path("pyproject.toml")
SCHEMA_VERSION = "risk-based-test-coverage-matrix.v1"
REQUIRED_MARKERS = {
    "api",
    "contract",
    "middleware",
    "security",
    "regression",
    "e2e",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _make_targets(repo_root: Path) -> set[str]:
    makefile = repo_root / "Makefile"
    if not makefile.exists():
        return set()
    targets: set[str] = set()
    target_pattern = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s|$)")
    for line in makefile.read_text(encoding="utf-8").splitlines():
        match = target_pattern.match(line)
        if match and not line.startswith("\t"):
            targets.add(match.group(1))
    return targets


def _repo_files(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode == 0:
        return [_normalize(line) for line in completed.stdout.splitlines() if line.strip()]
    return [
        path.relative_to(repo_root).as_posix()
        for path in repo_root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]


def _glob_matches(path: str, pattern: str) -> bool:
    regex_parts = ["^"]
    index = 0
    while index < len(pattern):
        if pattern[index : index + 3] == "**/":
            regex_parts.append("(?:.*/)?")
            index += 3
        elif pattern[index : index + 2] == "**":
            regex_parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            regex_parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            regex_parts.append("[^/]")
            index += 1
        else:
            regex_parts.append(re.escape(pattern[index]))
            index += 1
    regex_parts.append("$")
    return re.match("".join(regex_parts), path) is not None


def _coverage_ref_exists(
    ref: str,
    *,
    repo_root: Path,
    repo_files: list[str],
    make_targets: set[str],
) -> bool:
    normalized = _normalize(ref)
    if normalized.startswith("make "):
        target = normalized.removeprefix("make ").split()[0]
        return target in make_targets
    if any(ch in normalized for ch in "*?"):
        return any(_glob_matches(path, normalized) for path in repo_files)
    return normalized in repo_files or (repo_root / normalized).exists()


def _pytest_markers(repo_root: Path) -> set[str]:
    text = (repo_root / PYPROJECT_PATH).read_text(encoding="utf-8")
    marker_names: set[str] = set()
    in_markers = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "markers = [":
            in_markers = True
            continue
        if in_markers and stripped == "]":
            break
        if in_markers and stripped.startswith('"'):
            marker_names.add(stripped.split(":", 1)[0].strip('"'))
    return marker_names


def validate_matrix(
    matrix: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if matrix.get("schema_version") != SCHEMA_VERSION:
        findings.append({"invalid_schema_version": matrix.get("schema_version")})
    if matrix.get("owning_repository") != "lotus-core":
        findings.append({"invalid_owning_repository": matrix.get("owning_repository")})
    if not matrix.get("update_policy", {}).get("gate_command"):
        findings.append({"missing": "update_policy.gate_command"})

    proof_families = set(matrix.get("proof_families", []))
    allowed_statuses = set(matrix.get("allowed_gap_statuses", []))
    required_domains = set(matrix.get("required_domains", []))
    domains = matrix.get("domains")
    if not isinstance(domains, list) or not domains:
        findings.append({"missing": "domains"})
        return findings

    marker_gap = sorted(REQUIRED_MARKERS - _pytest_markers(repo_root))
    if marker_gap:
        findings.append({"missing_pytest_markers": marker_gap})

    repo_files = _repo_files(repo_root)
    make_targets = _make_targets(repo_root)
    seen_domains: set[str] = set()
    for domain in domains:
        if not isinstance(domain, dict):
            findings.append({"invalid_domain": domain})
            continue
        domain_id = str(domain.get("id", ""))
        if not domain_id:
            findings.append({"domain": domain, "missing": "id"})
            continue
        if domain_id in seen_domains:
            findings.append({"duplicate_domain": domain_id})
        seen_domains.add(domain_id)

        required = domain.get("required_proof_families")
        if not isinstance(required, list) or not required:
            findings.append({"domain": domain_id, "missing": "required_proof_families"})
            continue
        unknown_required = sorted(
            str(family) for family in required if family not in proof_families
        )
        if unknown_required:
            findings.append({"domain": domain_id, "unknown_required_families": unknown_required})

        coverage = domain.get("coverage")
        if not isinstance(coverage, list) or not coverage:
            findings.append({"domain": domain_id, "missing": "coverage"})
            continue

        coverage_by_family: dict[str, dict[str, Any]] = {}
        for entry in coverage:
            if not isinstance(entry, dict):
                findings.append({"domain": domain_id, "invalid_coverage_entry": entry})
                continue
            family = str(entry.get("proof_family", ""))
            if family in coverage_by_family:
                findings.append({"domain": domain_id, "duplicate_coverage_family": family})
            coverage_by_family[family] = entry
            if family not in proof_families:
                findings.append({"domain": domain_id, "unknown_coverage_family": family})
            status = str(entry.get("gap_status", ""))
            if status not in allowed_statuses:
                findings.append(
                    {"domain": domain_id, "family": family, "invalid_gap_status": status}
                )
            refs = entry.get("current_coverage")
            if not isinstance(refs, list) or not refs:
                findings.append(
                    {"domain": domain_id, "family": family, "missing": "current_coverage"}
                )
            else:
                missing_refs = [
                    str(ref)
                    for ref in refs
                    if not _coverage_ref_exists(
                        str(ref),
                        repo_root=repo_root,
                        repo_files=repo_files,
                        make_targets=make_targets,
                    )
                ]
                if missing_refs:
                    findings.append(
                        {
                            "domain": domain_id,
                            "family": family,
                            "coverage_refs_without_matches": missing_refs,
                        }
                    )
            if status != "covered" and not entry.get("follow_up_issue"):
                findings.append(
                    {"domain": domain_id, "family": family, "missing": "follow_up_issue"}
                )

        missing_families = sorted(
            str(family) for family in required if family not in coverage_by_family
        )
        if missing_families:
            findings.append({"domain": domain_id, "missing_required_families": missing_families})

    missing_domains = sorted(required_domains - seen_domains)
    if missing_domains:
        findings.append({"missing_required_domains": missing_domains})
    extra_domains = sorted(seen_domains - required_domains)
    if extra_domains:
        findings.append({"unexpected_domains": extra_domains})
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = validate_matrix(_load_json(REPO_ROOT / args.matrix), repo_root=REPO_ROOT)
    if findings:
        print("Risk-based test coverage matrix guard failed:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    print(f"Risk-based test coverage matrix guard passed: {args.matrix.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
