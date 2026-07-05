"""Guard committed synthetic fixtures, examples, and evidence surfaces from data leakage."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STANDARD_PATH = REPO_ROOT / "docs" / "standards" / "synthetic-test-data-governance.v1.json"
SCHEMA_VERSION = "synthetic-test-data-governance.v1"
GUARD_COMMAND = "make synthetic-fixture-leakage-guard"
REQUIRED_RELATIONSHIPS = {
    "client",
    "account",
    "portfolio",
    "custody",
    "instrument",
    "transaction",
    "cash",
    "fx",
    "benchmark",
    "reporting_currency",
}
TEXT_EXTENSIONS = {".json", ".md", ".py", ".txt", ".log", ".yaml", ".yml"}
SKIPPED_PATH_PARTS = {".git", ".venv", "node_modules", "__pycache__"}
PLACEHOLDER_VALUES = {
    "",
    "<redacted>",
    "<token>",
    "<api-key>",
    "<password>",
    "redacted",
    "masked",
    "***REDACTED***",
}
BEARER_RE = re.compile(
    r"(?i)\bBearer\s+(?!<redacted>\b|<token>\b|redacted\b)(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{8,}"
)
DATABASE_URL_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^:\s/@]+:[^@\s]+@"
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
CLIENT_NAME_JSON_RE = re.compile(
    r'"(?:client_display_name|client_name)"\s*:\s*"((?!SYNTH_|Synthetic |Example |Demo )[A-Z][a-z]+ [A-Z][a-z]+)"'
)
CLIENT_NAME_MD_RE = re.compile(
    r"(?i)client display name:\s*`((?!SYNTH_|Synthetic |Example |Demo )[A-Z][a-z]+ [A-Z][a-z]+)`"
)
ACCOUNT_NUMBER_RE = re.compile(
    r'"account_number"\s*:\s*"(?!<redacted>|SYNTH_|Example |Demo )([^"]+)"',
    re.IGNORECASE,
)
CIF_ID_RE = re.compile(r"\bCIF_[A-Z]{2}_\d{6}\b")
SECRET_FIELD_RE = re.compile(
    r'"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|secret|password|authorization)"\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SyntheticFixtureFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def load_standard(path: Path = STANDARD_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_synthetic_fixture_governance(
    *,
    repo_root: Path = REPO_ROOT,
    standard_path: Path | None = None,
) -> list[SyntheticFixtureFinding]:
    repo_root = repo_root.resolve()
    standard_path = standard_path or repo_root / STANDARD_PATH.relative_to(REPO_ROOT)
    if not standard_path.exists():
        return [
            SyntheticFixtureFinding(
                path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-standard",
                detail="synthetic test-data governance standard is missing",
            )
        ]

    standard = load_standard(standard_path)
    findings = _validate_standard(standard, repo_root=repo_root)
    allowed_cif_ids = {
        str(item.get("identifier"))
        for item in standard.get("canonical_synthetic_identifiers", [])
        if isinstance(item, dict)
    }
    for path in _candidate_files(repo_root, standard):
        findings.extend(_evaluate_file(path, repo_root=repo_root, allowed_cif_ids=allowed_cif_ids))
    return findings


def _validate_standard(
    standard: dict[str, Any],
    *,
    repo_root: Path,
) -> list[SyntheticFixtureFinding]:
    findings: list[SyntheticFixtureFinding] = []
    standard_rel = STANDARD_PATH.relative_to(REPO_ROOT).as_posix()
    if standard.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            SyntheticFixtureFinding(
                path=standard_rel,
                rule="invalid-schema-version",
                detail=f"expected {SCHEMA_VERSION}",
            )
        )
    if standard.get("owning_repository") != "lotus-core":
        findings.append(
            SyntheticFixtureFinding(
                path=standard_rel,
                rule="invalid-owning-repository",
                detail="owning_repository must be lotus-core",
            )
        )
    if standard.get("guard_command") != GUARD_COMMAND:
        findings.append(
            SyntheticFixtureFinding(
                path=standard_rel,
                rule="invalid-guard-command",
                detail=f"guard_command must be {GUARD_COMMAND}",
            )
        )
    _validate_scanned_globs(standard, findings)
    _validate_canonical_identifiers(standard, findings)
    _validate_fixture_catalog(standard, repo_root=repo_root, findings=findings)
    return findings


def _validate_scanned_globs(
    standard: dict[str, Any],
    findings: list[SyntheticFixtureFinding],
) -> None:
    guard = standard.get("leakage_guard", {})
    scanned_globs = guard.get("scanned_path_globs")
    if not isinstance(scanned_globs, list) or not all(
        isinstance(item, str) and item for item in scanned_globs
    ):
        findings.append(
            SyntheticFixtureFinding(
                path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="invalid-scan-scope",
                detail="leakage_guard.scanned_path_globs must be a non-empty string list",
            )
        )


def _validate_canonical_identifiers(
    standard: dict[str, Any],
    findings: list[SyntheticFixtureFinding],
) -> None:
    catalog = standard.get("canonical_synthetic_identifiers")
    if not isinstance(catalog, list):
        findings.append(
            SyntheticFixtureFinding(
                path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-canonical-synthetic-identifiers",
                detail="canonical_synthetic_identifiers must be a list",
            )
        )
        return
    seen: set[str] = set()
    for item in catalog:
        identifier = item.get("identifier") if isinstance(item, dict) else None
        if not isinstance(identifier, str) or not identifier:
            findings.append(
                SyntheticFixtureFinding(
                    path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="invalid-canonical-synthetic-identifier",
                    detail="each canonical identifier requires identifier",
                )
            )
            continue
        if identifier in seen:
            findings.append(
                SyntheticFixtureFinding(
                    path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="duplicate-canonical-synthetic-identifier",
                    detail=identifier,
                )
            )
        seen.add(identifier)
        if not item.get("synthetic_evidence"):
            findings.append(
                SyntheticFixtureFinding(
                    path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="missing-synthetic-evidence",
                    detail=identifier,
                )
            )


def _validate_fixture_catalog(
    standard: dict[str, Any],
    *,
    repo_root: Path,
    findings: list[SyntheticFixtureFinding],
) -> None:
    catalog = standard.get("fixture_catalog")
    if not isinstance(catalog, list) or not catalog:
        findings.append(
            SyntheticFixtureFinding(
                path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-fixture-catalog",
                detail="fixture_catalog must contain reusable fixture entries",
            )
        )
        return

    representative_found = False
    for item in catalog:
        if not isinstance(item, dict):
            findings.append(
                SyntheticFixtureFinding(
                    path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="invalid-fixture-catalog-entry",
                    detail="fixture entries must be objects",
                )
            )
            continue
        fixture_path = item.get("path")
        if not isinstance(fixture_path, str) or not fixture_path:
            findings.append(
                SyntheticFixtureFinding(
                    path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="missing-fixture-path",
                    detail=str(item.get("fixture_id", "<missing-fixture-id>")),
                )
            )
            continue
        resolved = repo_root / fixture_path
        if not resolved.exists():
            findings.append(
                SyntheticFixtureFinding(
                    path=fixture_path,
                    rule="missing-fixture-file",
                    detail="cataloged fixture path does not exist",
                )
            )
            continue
        if fixture_path == "tests/fixtures/private-banking-portfolio-fixture.v1.json":
            representative_found = True
            _validate_representative_fixture(resolved, repo_root=repo_root, findings=findings)
    if not representative_found:
        findings.append(
            SyntheticFixtureFinding(
                path=STANDARD_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-representative-private-banking-fixture",
                detail="fixture_catalog must include tests/fixtures/private-banking-portfolio-fixture.v1.json",
            )
        )


def _validate_representative_fixture(
    fixture_path: Path,
    *,
    repo_root: Path,
    findings: list[SyntheticFixtureFinding],
) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_rel = fixture_path.relative_to(repo_root).as_posix()
    relationships = fixture.get("relationships")
    if not fixture.get("synthetic_data") or not fixture.get("safe_for_committed_tests"):
        findings.append(
            SyntheticFixtureFinding(
                path=fixture_rel,
                rule="representative-fixture-not-marked-safe",
                detail="fixture must set synthetic_data and safe_for_committed_tests",
            )
        )
    if not isinstance(relationships, dict):
        findings.append(
            SyntheticFixtureFinding(
                path=fixture_rel,
                rule="missing-representative-relationships",
                detail="relationships must be an object",
            )
        )
        return
    missing = REQUIRED_RELATIONSHIPS - set(relationships)
    if missing:
        findings.append(
            SyntheticFixtureFinding(
                path=fixture_rel,
                rule="missing-representative-relationship",
                detail=", ".join(sorted(missing)),
            )
        )


def _candidate_files(repo_root: Path, standard: dict[str, Any]) -> list[Path]:
    guard = standard.get("leakage_guard", {})
    globs = list(guard.get("scanned_path_globs", []))
    globs.extend(guard.get("optional_generated_evidence_globs", []))
    matched: set[Path] = set()
    for pattern in globs:
        for path in repo_root.glob(pattern):
            if path.is_file() and _is_text_candidate(path):
                matched.add(path.resolve())
    matched.update(_tracked_files_matching(repo_root, globs))
    return sorted(matched)


def _tracked_files_matching(repo_root: Path, globs: list[str]) -> set[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return set()
    matched: set[Path] = set()
    for line in result.stdout.splitlines():
        normalized = line.replace("\\", "/")
        if any(fnmatch.fnmatch(normalized, pattern) for pattern in globs):
            path = (repo_root / normalized).resolve()
            if path.is_file() and _is_text_candidate(path):
                matched.add(path)
    return matched


def _is_text_candidate(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    return not any(part in SKIPPED_PATH_PARTS for part in path.parts)


def _evaluate_file(
    path: Path,
    *,
    repo_root: Path,
    allowed_cif_ids: set[str],
) -> list[SyntheticFixtureFinding]:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(repo_root).as_posix()
    findings: list[SyntheticFixtureFinding] = []
    _append_regex_findings(findings, rel, "concrete-bearer-token", BEARER_RE, text)
    _append_regex_findings(findings, rel, "credentialed-database-url", DATABASE_URL_RE, text)
    _append_regex_findings(findings, rel, "personal-email-address", EMAIL_RE, text)
    _append_regex_findings(findings, rel, "real-looking-client-name", CLIENT_NAME_JSON_RE, text)
    _append_regex_findings(findings, rel, "real-looking-client-name", CLIENT_NAME_MD_RE, text)
    _append_regex_findings(findings, rel, "concrete-account-number", ACCOUNT_NUMBER_RE, text)
    for value in sorted(set(CIF_ID_RE.findall(text)) - allowed_cif_ids):
        findings.append(
            SyntheticFixtureFinding(
                path=rel,
                rule="uncataloged-cif-client-id",
                detail=value,
            )
        )
    for match in SECRET_FIELD_RE.finditer(text):
        value = match.group(1).strip()
        if value not in PLACEHOLDER_VALUES and not value.lower().startswith("bearer <redacted>"):
            findings.append(
                SyntheticFixtureFinding(
                    path=rel,
                    rule="concrete-secret-field",
                    detail=_redact_detail(value),
                )
            )
    return findings


def _append_regex_findings(
    findings: list[SyntheticFixtureFinding],
    path: str,
    rule: str,
    pattern: re.Pattern[str],
    text: str,
) -> None:
    for match in pattern.finditer(text):
        findings.append(
            SyntheticFixtureFinding(
                path=path,
                rule=rule,
                detail=_redact_detail(match.group(0)),
            )
        )


def _redact_detail(value: str) -> str:
    if len(value) <= 24:
        return value
    return f"{value[:12]}...{value[-6:]}"


def main() -> int:
    findings = evaluate_synthetic_fixture_governance()
    if findings:
        print("Synthetic fixture leakage guard failed:")
        for finding in findings:
            print(f"- {finding.as_text()}")
        return 1
    print("Synthetic fixture leakage guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
