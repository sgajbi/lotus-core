from __future__ import annotations

import json
from pathlib import Path

from scripts import supported_features_guard as guard


def _base_capability(**overrides) -> dict[str, object]:
    capability: dict[str, object] = {
        "id": "portfolio-account-source-record",
        "display_name": "Portfolio and account source of record",
        "owner": "lotus-core",
        "status": "supported",
        "implementation_modules": ["src/service.py"],
        "routes": ["/portfolios/{portfolio_id}"],
        "source_data_products": ["HoldingsAsOf:v1"],
        "tests": ["tests/test_service.py"],
        "validation_evidence": ["make lotus-core-validate", "docs/evidence.md"],
        "safe_demo_claims": [
            {
                "claim": "Core provides recorded portfolio source truth.",
                "evidence_refs": ["docs/evidence.md"],
            }
        ],
        "prohibited_claims": [
            {
                "claim": "Core owns performance conclusions.",
                "owning_service_boundary": "lotus-performance",
                "evidence_refs": ["docs/evidence.md"],
            }
        ],
        "limitations": ["Source truth is bounded to persisted Core records."],
        "downstream_ownership_caveats": ["Downstream conclusions remain downstream-owned."],
    }
    capability.update(overrides)
    return capability


def _write_repo(tmp_path: Path, *, capability: dict[str, object] | None = None) -> Path:
    capability = capability or _base_capability()
    manifest_path = tmp_path / guard.MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": guard.EXPECTED_SCHEMA_VERSION,
                "repository": "lotus-core",
                "documentation_surfaces": [
                    "docs/supported-features.md",
                    "wiki/Supported-Features.md",
                ],
                "guard_command": "make supported-features-guard",
                "capabilities": [capability],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    domain_contract = tmp_path / guard.DOMAIN_PRODUCTS_PATH
    domain_contract.parent.mkdir(parents=True)
    domain_contract.write_text(
        json.dumps(
            {
                "products": [
                    {"product_name": "HoldingsAsOf", "product_version": "v1"},
                ]
            }
        ),
        encoding="utf-8",
    )
    for relative_path in (
        "src/service.py",
        "tests/test_service.py",
        "docs/evidence.md",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
    docs_text = "\n".join(
        [
            guard.MANIFEST_PATH.as_posix(),
            "make supported-features-guard",
            "Portfolio and account source of record",
            "supported",
        ]
    )
    wiki_text = "\n".join(
        [
            guard.MANIFEST_PATH.as_posix(),
            "make supported-features-guard",
            "Portfolio and account source of record",
        ]
    )
    (tmp_path / "docs" / "supported-features.md").write_text(docs_text, encoding="utf-8")
    wiki_path = tmp_path / "wiki" / "Supported-Features.md"
    wiki_path.parent.mkdir(parents=True)
    wiki_path.write_text(wiki_text, encoding="utf-8")
    return tmp_path


def test_supported_features_guard_accepts_manifest_backed_docs(tmp_path: Path) -> None:
    repo = _write_repo(tmp_path)

    assert guard.find_supported_feature_findings(repo) == []


def test_supported_features_guard_rejects_missing_documented_capability(
    tmp_path: Path,
) -> None:
    repo = _write_repo(tmp_path)
    (repo / "wiki" / "Supported-Features.md").write_text(
        f"{guard.MANIFEST_PATH.as_posix()}\nmake supported-features-guard\n",
        encoding="utf-8",
    )

    findings = guard.find_supported_feature_findings(repo)

    assert any("missing capability display name" in finding.detail for finding in findings)


def test_supported_features_guard_rejects_invalid_evidence_reference(
    tmp_path: Path,
) -> None:
    repo = _write_repo(
        tmp_path,
        capability=_base_capability(validation_evidence=["docs/missing-evidence.md"]),
    )

    findings = guard.find_supported_feature_findings(repo)

    assert any("validation evidence reference is invalid" in finding.detail for finding in findings)


def test_supported_features_guard_rejects_unknown_domain_product(
    tmp_path: Path,
) -> None:
    repo = _write_repo(
        tmp_path,
        capability=_base_capability(source_data_products=["UnknownProduct:v1"]),
    )

    findings = guard.find_supported_feature_findings(repo)

    assert any("not in domain product contract" in finding.detail for finding in findings)


def test_supported_features_guard_requires_fail_closed_limitation(
    tmp_path: Path,
) -> None:
    repo = _write_repo(
        tmp_path,
        capability=_base_capability(
            status="supported_with_fail_closed_dependencies",
            limitations=["External data dependency is explicit."],
        ),
    )

    findings = guard.find_supported_feature_findings(repo)

    assert any("fail-closed capability status" in finding.detail for finding in findings)
