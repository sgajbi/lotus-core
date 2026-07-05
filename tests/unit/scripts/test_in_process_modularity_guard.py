import json
from pathlib import Path

from scripts.in_process_modularity_guard import find_in_process_modularity_findings


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_paths(root: Path) -> None:
    for path in (
        "docs/standards/in-process-modularity-package-standard.md",
        "docs/architecture/evidence.md",
        "src/services/example_service/app/application/__init__.py",
        "src/services/example_service/app/domain/__init__.py",
        "src/services/example_service/app/ports/__init__.py",
        "src/services/example_service/app/adapters/__init__.py",
        "src/services/example_service/app/infrastructure/__init__.py",
        "src/services/example_service/app/routers/__init__.py",
        "src/services/example_service/app/repositories/__init__.py",
        "src/services/example_service/app/consumers/__init__.py",
        "src/services/example_service/app/DTOs/__init__.py",
        "src/services/example_service/app/services/__init__.py",
        "src/services/example_service/app/dependencies.py",
        "src/services/example_service/app/main.py",
    ):
        _write(root / path, "")


def _catalog_payload(
    *,
    required_package_paths: list[str] | None = None,
    evidence: list[str] | None = None,
    legacy_folders: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "standardPath": "docs/standards/in-process-modularity-package-standard.md",
        "representativeAdoptions": [
            {
                "serviceId": "example_service",
                "servicePath": "src/services/example_service",
                "status": "representative-adopted-with-legacy-folders",
                "requiredPackagePaths": required_package_paths
                if required_package_paths is not None
                else [
                    "src/services/example_service/app/application",
                    "src/services/example_service/app/domain",
                    "src/services/example_service/app/ports",
                    "src/services/example_service/app/adapters",
                    "src/services/example_service/app/infrastructure",
                    "src/services/example_service/app/routers",
                    "src/services/example_service/app/repositories",
                ],
                "runtimeCompositionFiles": [
                    "src/services/example_service/app/dependencies.py",
                    "src/services/example_service/app/main.py",
                ],
                "deliveryPackagePaths": [
                    "src/services/example_service/app/routers",
                    "src/services/example_service/app/consumers",
                ],
                "legacyFolders": legacy_folders
                if legacy_folders is not None
                else [
                    {
                        "path": "src/services/example_service/app/DTOs",
                        "migrationGuidance": "Keep API DTOs at delivery boundaries.",
                    },
                    {
                        "path": "src/services/example_service/app/services",
                        "migrationGuidance": "Extract cohesive workflows as touched.",
                    },
                ],
                "evidence": evidence if evidence is not None else ["docs/architecture/evidence.md"],
                "noRuntimeSplitRationale": "Design modularity only.",
            }
        ],
    }


def _write_catalog(root: Path, payload: dict[str, object]) -> None:
    _write(
        root / "docs/architecture/in-process-modularity-adoption-catalog.json",
        json.dumps(payload, indent=2),
    )


def test_in_process_modularity_guard_allows_representative_adoption(
    tmp_path: Path,
) -> None:
    _write_required_paths(tmp_path)
    _write_catalog(tmp_path, _catalog_payload())

    assert find_in_process_modularity_findings(tmp_path) == []


def test_in_process_modularity_guard_rejects_missing_required_package(
    tmp_path: Path,
) -> None:
    _write_required_paths(tmp_path)
    _write_catalog(
        tmp_path,
        _catalog_payload(
            required_package_paths=[
                "src/services/example_service/app/application",
                "src/services/example_service/app/missing_package",
            ]
        ),
    )

    findings = find_in_process_modularity_findings(tmp_path)

    assert any(finding.rule == "missing-adoption-path" for finding in findings)


def test_in_process_modularity_guard_rejects_missing_evidence(
    tmp_path: Path,
) -> None:
    _write_required_paths(tmp_path)
    _write_catalog(tmp_path, _catalog_payload(evidence=["docs/architecture/missing.md"]))

    findings = find_in_process_modularity_findings(tmp_path)

    assert any(finding.rule == "missing-adoption-evidence" for finding in findings)


def test_in_process_modularity_guard_rejects_unclassified_legacy_folder(
    tmp_path: Path,
) -> None:
    _write_required_paths(tmp_path)
    _write_catalog(tmp_path, _catalog_payload(legacy_folders=[]))

    findings = find_in_process_modularity_findings(tmp_path)

    assert any(finding.rule == "missing-legacy-folder-classification" for finding in findings)
