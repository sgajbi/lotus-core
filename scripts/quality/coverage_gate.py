"""Run or combine governed coverage with exact-source artifact identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure repository root is importable when script runs directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Coverage.py enforces the displayed integer total for the combined
# branch-aware unit + integration-lite gate.
FAIL_UNDER = "98"
COVERAGE_OUTPUT_DIR = REPO_ROOT / "output" / "coverage"
COVERAGE_JSON = COVERAGE_OUTPUT_DIR / "coverage.json"
QUERY_SERVICE_COVERAGE_JSON = COVERAGE_OUTPUT_DIR / "query-service-coverage.json"
CRITICAL_PATH_REPORT = COVERAGE_OUTPUT_DIR / "critical-path-coverage-report.json"
UNIT_WARNING_BUDGET = 0
QUERY_SERVICE_INCLUDE = "src/services/query_service/app/*"
COVERAGE_ARTIFACT_SCHEMA = 1
COVERAGE_SUITES = (
    "unit",
    "unit-db",
    "critical-db-coverage",
    "integration-lite",
    "ops-contract",
)
COVERAGE_STEMS = {
    "unit": "unit",
    "unit-db": "unit_db",
    "critical-db-coverage": "critical_db",
    "integration-lite": "integration_lite",
    "ops-contract": "ops_contract",
}
CONFIG_PATHS = (
    Path("pyproject.toml"),
    Path("scripts/quality/test_manifest.py"),
    Path("docs/standards/critical-path-coverage.v1.json"),
)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _changed_critical_paths() -> tuple[str, ...]:
    from scripts.quality.coverage_evidence.changed_source_evidence import (
        read_git_changed_sources,
    )
    from scripts.quality.critical_path_coverage_guard import (
        CONTRACT_PATH,
        changed_critical_source_paths,
    )

    contract = json.loads((REPO_ROOT / CONTRACT_PATH).read_text(encoding="utf-8"))
    changed_base = os.environ.get(
        "LOTUS_COVERAGE_CHANGED_BASE",
        str(contract["changed_code_gate"]["default_base_ref"]),
    )
    changes = read_git_changed_sources(repo_root=REPO_ROOT, base_ref=changed_base)
    return tuple(changed_critical_source_paths(changes, contract=contract))


def _coverage_sources(critical_paths: tuple[str, ...]) -> tuple[str, ...]:
    from scripts.quality.coverage_evidence.changed_source_evidence import coverage_source_target
    from scripts.quality.test_manifest import SOURCE

    changed_targets = (coverage_source_target(path) for path in critical_paths)
    return tuple(dict.fromkeys((SOURCE, *changed_targets)))


def _coverage_include(critical_paths: tuple[str, ...]) -> str:
    """Limit JSON evidence to aggregate scope plus exact changed critical files."""

    normalized_for_host = (str(Path(path)) for path in (QUERY_SERVICE_INCLUDE, *critical_paths))
    return ",".join(dict.fromkeys(normalized_for_host))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _configuration_digests() -> dict[str, str]:
    return {path.as_posix(): _sha256(REPO_ROOT / path) for path in CONFIG_PATHS}


def _source_head() -> str:
    return _resolve_revision("HEAD")


def _resolve_revision(revision: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--verify", revision],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _tracked_source_is_clean() -> bool:
    return (
        subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--"],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )


def _validate_source_identity(*, head_sha: str, base_ref: str) -> None:
    if not head_sha or not base_ref:
        raise ValueError("coverage artifact identity requires non-empty head SHA and base ref")
    actual_head = _source_head()
    if actual_head != head_sha:
        raise ValueError(
            f"coverage artifact head mismatch: requested {head_sha}, checkout is {actual_head}"
        )
    if not _tracked_source_is_clean():
        raise ValueError("coverage artifacts require a clean tracked source checkout")


def _artifact_stem(suite: str) -> str:
    return COVERAGE_STEMS[suite]


def _run_coverage_suite(
    suite: str,
    *,
    coverage_sources: tuple[str, ...],
    coverage_file: str,
) -> int:
    from scripts.quality.test_manifest import run_suite
    from scripts.quality.warning_budget_gate import run_suite_with_warning_budget

    if suite == "unit":
        return int(
            run_suite_with_warning_budget(
                suite="unit",
                max_warnings=UNIT_WARNING_BUDGET,
                with_coverage=True,
                coverage_sources=coverage_sources,
                coverage_file=coverage_file,
            )
        )
    return int(
        run_suite(
            suite,
            with_coverage=True,
            coverage_sources=coverage_sources,
            coverage_file=coverage_file,
        )
    )


def _write_shard_artifact(*, suite: str, artifact_dir: Path, head_sha: str, base_ref: str) -> int:
    if suite not in COVERAGE_SUITES:
        raise ValueError(f"unsupported coverage shard: {suite}")
    _validate_source_identity(head_sha=head_sha, base_ref=base_ref)
    os.environ["LOTUS_COVERAGE_CHANGED_BASE"] = base_ref
    critical_paths = _changed_critical_paths()
    coverage_sources = _coverage_sources(critical_paths)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = _artifact_stem(suite)
    data_path = artifact_dir / f"coverage-{stem}.data"
    metadata_path = artifact_dir / f"coverage-{stem}.json"
    data_path.unlink(missing_ok=True)
    metadata_path.unlink(missing_ok=True)
    if (
        _run_coverage_suite(
            suite,
            coverage_sources=coverage_sources,
            coverage_file=str(data_path),
        )
        != 0
    ):
        return 1
    if not data_path.is_file() or data_path.stat().st_size == 0:
        raise ValueError(f"coverage shard {suite} produced no coverage data")
    metadata = {
        "schema_version": COVERAGE_ARTIFACT_SCHEMA,
        "suite": suite,
        "head_sha": head_sha,
        "base_ref": base_ref,
        "base_sha": _resolve_revision(base_ref),
        "coverage_sources": list(coverage_sources),
        "critical_paths": list(critical_paths),
        "configuration_sha256": _configuration_digests(),
        "data_file": data_path.name,
        "data_sha256": _sha256(data_path),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid coverage metadata {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"coverage metadata {path} must contain an object")
    return document


def _validated_artifacts(*, artifact_dir: Path, head_sha: str, base_ref: str) -> dict[str, Path]:
    _validate_source_identity(head_sha=head_sha, base_ref=base_ref)
    os.environ["LOTUS_COVERAGE_CHANGED_BASE"] = base_ref
    expected_critical_paths = list(_changed_critical_paths())
    expected_sources = list(_coverage_sources(tuple(expected_critical_paths)))
    expected_config = _configuration_digests()
    artifacts: dict[str, Path] = {}
    metadata_paths = sorted(artifact_dir.rglob("coverage-*.json"))
    for metadata_path in metadata_paths:
        metadata = _load_metadata(metadata_path)
        suite = metadata.get("suite")
        if suite not in COVERAGE_SUITES:
            raise ValueError(f"coverage metadata {metadata_path} has unsupported suite {suite!r}")
        if suite in artifacts:
            raise ValueError(f"duplicate coverage artifact for suite {suite}")
        expected_identity = {
            "schema_version": COVERAGE_ARTIFACT_SCHEMA,
            "head_sha": head_sha,
            "base_ref": base_ref,
            "base_sha": _resolve_revision(base_ref),
            "coverage_sources": expected_sources,
            "critical_paths": expected_critical_paths,
            "configuration_sha256": expected_config,
        }
        for field, expected in expected_identity.items():
            if metadata.get(field) != expected:
                raise ValueError(
                    f"coverage artifact {suite} has incompatible {field}: "
                    f"expected {expected!r}, got {metadata.get(field)!r}"
                )
        data_file = metadata.get("data_file")
        if not isinstance(data_file, str) or Path(data_file).name != data_file:
            raise ValueError(f"coverage artifact {suite} has invalid data_file")
        data_path = metadata_path.parent / data_file
        if not data_path.is_file() or data_path.stat().st_size == 0:
            raise ValueError(f"coverage artifact {suite} has missing or empty data")
        if metadata.get("data_sha256") != _sha256(data_path):
            raise ValueError(f"coverage artifact {suite} failed checksum verification")
        artifacts[suite] = data_path
    missing = sorted(set(COVERAGE_SUITES) - artifacts.keys())
    if missing:
        raise ValueError(f"missing coverage artifacts: {', '.join(missing)}")
    return artifacts


def _enforce_combined_coverage(critical_paths: tuple[str, ...]) -> None:
    run([sys.executable, "-m", "coverage", "combine"])
    run(
        [
            sys.executable,
            "-m",
            "coverage",
            "report",
            f"--include={QUERY_SERVICE_INCLUDE}",
            f"--fail-under={FAIL_UNDER}",
        ]
    )
    COVERAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "-m",
            "coverage",
            "json",
            f"--include={QUERY_SERVICE_INCLUDE}",
            "-o",
            str(QUERY_SERVICE_COVERAGE_JSON),
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "coverage",
            "json",
            f"--include={_coverage_include(critical_paths)}",
            "-o",
            str(COVERAGE_JSON),
        ]
    )
    run(
        [
            sys.executable,
            "scripts/quality/critical_path_coverage_guard.py",
            "--coverage-json",
            str(COVERAGE_JSON.relative_to(REPO_ROOT)),
            "--aggregate-coverage-json",
            str(QUERY_SERVICE_COVERAGE_JSON.relative_to(REPO_ROOT)),
            "--output",
            str(CRITICAL_PATH_REPORT.relative_to(REPO_ROOT)),
        ]
    )


def _aggregate_artifacts(*, artifact_dir: Path, head_sha: str, base_ref: str) -> int:
    artifacts = _validated_artifacts(
        artifact_dir=artifact_dir,
        head_sha=head_sha,
        base_ref=base_ref,
    )
    _clean_combined_files()
    for suite, data_path in artifacts.items():
        shutil.copyfile(data_path, REPO_ROOT / f".coverage.{_artifact_stem(suite)}")
    _enforce_combined_coverage(_changed_critical_paths())
    return 0


def _clean_combined_files() -> None:
    for artifact in REPO_ROOT.glob(".coverage*"):
        if artifact.is_file():
            artifact.unlink()


def _run_local_gate() -> int:
    critical_paths = _changed_critical_paths()
    coverage_sources = _coverage_sources(critical_paths)
    _clean_combined_files()
    for suite in COVERAGE_SUITES:
        if (
            _run_coverage_suite(
                suite,
                coverage_sources=coverage_sources,
                coverage_file=f".coverage.{_artifact_stem(suite)}",
            )
            != 0
        ):
            return 1
    _enforce_combined_coverage(critical_paths)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--shard", choices=COVERAGE_SUITES)
    mode.add_argument("--aggregate-artifacts", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--head-sha")
    parser.add_argument("--base-ref")
    return parser


def main(argv: list[str] | tuple[str, ...] = ()) -> int:
    args = _parser().parse_args(argv)
    if args.shard:
        head_sha = args.head_sha or os.environ.get("GITHUB_SHA") or _source_head()
        base_ref = args.base_ref or os.environ.get("LOTUS_COVERAGE_CHANGED_BASE")
        if args.artifact_dir is None or base_ref is None:
            raise ValueError("shard mode requires artifact dir and changed base ref")
        return _write_shard_artifact(
            suite=args.shard,
            artifact_dir=args.artifact_dir,
            head_sha=head_sha,
            base_ref=base_ref,
        )
    if args.aggregate_artifacts:
        head_sha = args.head_sha or os.environ.get("GITHUB_SHA") or _source_head()
        base_ref = args.base_ref or os.environ.get("LOTUS_COVERAGE_CHANGED_BASE")
        if base_ref is None:
            raise ValueError("aggregate mode requires changed base ref")
        return _aggregate_artifacts(
            artifact_dir=args.aggregate_artifacts,
            head_sha=head_sha,
            base_ref=base_ref,
        )
    return _run_local_gate()


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ValueError as exc:
        print(f"coverage gate failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
