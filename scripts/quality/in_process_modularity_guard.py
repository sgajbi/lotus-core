from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATALOG_PATH = Path("docs/architecture/in-process-modularity-adoption-catalog.json")
STANDARD_PATH = Path("docs/standards/in-process-modularity-package-standard.md")
VALID_STATUSES = {
    "representative-adopted",
    "representative-adopted-with-legacy-folders",
    "partial-adoption",
}


@dataclass(frozen=True, slots=True)
class InProcessModularityFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def find_in_process_modularity_findings(root: Path) -> list[InProcessModularityFinding]:
    root = root.resolve()
    findings: list[InProcessModularityFinding] = []
    catalog = _load_catalog(root, findings)
    if catalog is None:
        return findings

    standard_path = catalog.get("standardPath")
    if standard_path != STANDARD_PATH.as_posix():
        findings.append(
            InProcessModularityFinding(
                path=CATALOG_PATH.as_posix(),
                rule="invalid-standard-path",
                detail=f"standardPath must be {STANDARD_PATH.as_posix()}",
            )
        )
    if not (root / STANDARD_PATH).exists():
        findings.append(
            InProcessModularityFinding(
                path=STANDARD_PATH.as_posix(),
                rule="missing-in-process-modularity-standard",
                detail="in-process modularity package standard is missing",
            )
        )

    adoptions = catalog.get("representativeAdoptions")
    if not isinstance(adoptions, list) or not adoptions:
        findings.append(
            InProcessModularityFinding(
                path=CATALOG_PATH.as_posix(),
                rule="missing-representative-adoption",
                detail="catalog must contain at least one representative adoption",
            )
        )
        return findings

    for adoption in adoptions:
        findings.extend(_validate_adoption(root, adoption))
    return findings


def _load_catalog(
    root: Path,
    findings: list[InProcessModularityFinding],
) -> dict[str, Any] | None:
    path = root / CATALOG_PATH
    if not path.exists():
        findings.append(
            InProcessModularityFinding(
                path=CATALOG_PATH.as_posix(),
                rule="missing-in-process-modularity-catalog",
                detail="in-process modularity adoption catalog is missing",
            )
        )
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_adoption(root: Path, adoption: object) -> list[InProcessModularityFinding]:
    if not isinstance(adoption, dict):
        return [
            InProcessModularityFinding(
                path=CATALOG_PATH.as_posix(),
                rule="invalid-representative-adoption",
                detail="representative adoption entries must be objects",
            )
        ]

    service_path = _string_field(adoption, "servicePath") or "<missing-service-path>"
    findings: list[InProcessModularityFinding] = []
    status = _string_field(adoption, "status")
    if status not in VALID_STATUSES:
        findings.append(
            InProcessModularityFinding(
                path=service_path,
                rule="invalid-adoption-status",
                detail=f"status must be one of {sorted(VALID_STATUSES)}",
            )
        )
    for field_name in ("serviceId", "servicePath", "noRuntimeSplitRationale"):
        if not _string_field(adoption, field_name):
            findings.append(
                InProcessModularityFinding(
                    path=service_path,
                    rule="missing-adoption-field",
                    detail=f"{field_name} must be a non-empty string",
                )
            )
    for field_name in (
        "requiredPackagePaths",
        "runtimeCompositionFiles",
        "deliveryPackagePaths",
        "evidence",
    ):
        values = _string_list_field(adoption, field_name)
        if values is None:
            findings.append(
                InProcessModularityFinding(
                    path=service_path,
                    rule="missing-adoption-list",
                    detail=f"{field_name} must be a non-empty string list",
                )
            )
            continue
        for value in values:
            if field_name == "evidence":
                if not (root / value).exists():
                    findings.append(
                        InProcessModularityFinding(
                            path=service_path,
                            rule="missing-adoption-evidence",
                            detail=f"evidence path does not exist: {value}",
                        )
                    )
            elif not (root / value).exists():
                findings.append(
                    InProcessModularityFinding(
                        path=service_path,
                        rule="missing-adoption-path",
                        detail=f"{field_name} path does not exist: {value}",
                    )
                )

    legacy_folders = adoption.get("legacyFolders")
    if status == "representative-adopted-with-legacy-folders":
        findings.extend(_validate_legacy_folders(root, service_path, legacy_folders))
    return findings


def _validate_legacy_folders(
    root: Path,
    service_path: str,
    legacy_folders: object,
) -> list[InProcessModularityFinding]:
    if not isinstance(legacy_folders, list) or not legacy_folders:
        return [
            InProcessModularityFinding(
                path=service_path,
                rule="missing-legacy-folder-classification",
                detail="legacyFolders must classify retained legacy folders",
            )
        ]
    findings: list[InProcessModularityFinding] = []
    for entry in legacy_folders:
        if not isinstance(entry, dict):
            findings.append(
                InProcessModularityFinding(
                    path=service_path,
                    rule="invalid-legacy-folder-entry",
                    detail="legacy folder entries must be objects",
                )
            )
            continue
        legacy_path = _string_field(entry, "path")
        guidance = _string_field(entry, "migrationGuidance")
        if not legacy_path or not guidance:
            findings.append(
                InProcessModularityFinding(
                    path=service_path,
                    rule="invalid-legacy-folder-entry",
                    detail="legacy folders require path and migrationGuidance",
                )
            )
            continue
        if not (root / legacy_path).exists():
            findings.append(
                InProcessModularityFinding(
                    path=service_path,
                    rule="missing-legacy-folder-path",
                    detail=f"legacy folder path does not exist: {legacy_path}",
                )
            )
    return findings


def _string_field(record: dict[str, Any], field_name: str) -> str | None:
    value = record.get(field_name)
    return value if isinstance(value, str) and value.strip() else None


def _string_list_field(record: dict[str, Any], field_name: str) -> list[str] | None:
    value = record.get(field_name)
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return value


def main() -> int:
    findings = find_in_process_modularity_findings(Path.cwd())
    if findings:
        print("In-process modularity guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("In-process modularity guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
