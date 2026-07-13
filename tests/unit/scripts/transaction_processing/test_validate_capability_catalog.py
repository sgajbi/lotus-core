"""Test transaction capability catalog governance."""

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.transaction_processing import validate_capability_catalog as guard


def _registry() -> dict[str, SimpleNamespace]:
    return {
        "BUY": SimpleNamespace(
            lifecycle_family="trade",
            economic_role="security_buy",
            calculation_support_status="supported",
            production_booking_allowed=True,
        ),
        "MATURITY_REDEMPTION": SimpleNamespace(
            lifecycle_family="redemption",
            economic_role="maturity_redemption",
            calculation_support_status="target_not_implemented",
            production_booking_allowed=False,
        ),
    }


def _catalog() -> dict[str, object]:
    return {
        "schema_version": guard.EXPECTED_SCHEMA_VERSION,
        "repository": "lotus-core",
        "source_registry": guard.REGISTRY_PATH.as_posix(),
        "guard_command": "make transaction-capability-catalog-guard",
        "generator_command": guard.GENERATOR_COMMAND,
        "documentation_surfaces": [
            "docs/features/transaction-and-product-lifecycle-capabilities.md",
            "wiki/Transaction-and-Product-Lifecycle-Capabilities.md",
        ],
        "transaction_types": [
            {
                "code": "BUY",
                "lifecycle_family": "trade",
                "economic_role": "security_buy",
                "support_status": "supported",
                "production_booking_allowed": True,
                "gap_issue": None,
            },
            {
                "code": "MATURITY_REDEMPTION",
                "lifecycle_family": "redemption",
                "economic_role": "maturity_redemption",
                "support_status": "target_not_implemented",
                "production_booking_allowed": False,
                "gap_issue": 477,
            },
        ],
        "product_lifecycles": [
            {
                "product_family": "listed_equity",
                "lifecycle_event": "trade",
                "transaction_types": ["BUY"],
                "support_status": "supported",
                "evidence_refs": ["tests/test_trade.py"],
                "limitations": ["Trade support does not certify every security lifecycle."],
                "gap_issues": [],
            },
            {
                "product_family": "fixed_income",
                "lifecycle_event": "maturity_redemption",
                "transaction_types": ["MATURITY_REDEMPTION"],
                "support_status": "target_not_implemented",
                "evidence_refs": ["docs/redemption.md"],
                "limitations": ["Production booking is disabled."],
                "gap_issues": [477],
            },
        ],
    }


def _write_repo(tmp_path: Path, payload: dict[str, object]) -> Path:
    catalog_path = tmp_path / guard.CATALOG_PATH
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(json.dumps(payload), encoding="utf-8")
    for relative_path in (
        "tests/test_trade.py",
        "docs/redemption.md",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence\n", encoding="utf-8")
    for relative_path in payload["documentation_surfaces"]:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"{guard.CATALOG_PATH.as_posix()}\nmake transaction-capability-catalog-guard\n",
            encoding="utf-8",
        )
    return tmp_path


def test_catalog_guard_accepts_registry_exact_and_issue_owned_gaps(tmp_path: Path) -> None:
    root = _write_repo(tmp_path, _catalog())

    assert guard.find_transaction_capability_findings(root, registry=_registry()) == []


def test_catalog_guard_rejects_registry_metadata_drift(tmp_path: Path) -> None:
    payload = _catalog()
    payload["transaction_types"][0]["economic_role"] = "generic_trade"
    root = _write_repo(tmp_path, payload)

    findings = guard.find_transaction_capability_findings(root, registry=_registry())

    assert any("economic_role must match registry" in finding.detail for finding in findings)


def test_catalog_guard_rejects_missing_or_duplicate_registry_codes(tmp_path: Path) -> None:
    payload = _catalog()
    payload["transaction_types"] = [payload["transaction_types"][0]] * 2
    root = _write_repo(tmp_path, payload)

    findings = guard.find_transaction_capability_findings(root, registry=_registry())

    assert any("duplicate transaction type BUY" in finding.detail for finding in findings)
    assert any(
        "missing registry transaction types: MATURITY_REDEMPTION" in finding.detail
        for finding in findings
    )


def test_catalog_guard_requires_issue_owner_for_unsupported_lifecycle(tmp_path: Path) -> None:
    payload = _catalog()
    payload["transaction_types"][1]["gap_issue"] = None
    payload["product_lifecycles"][1]["gap_issues"] = []
    root = _write_repo(tmp_path, payload)

    findings = guard.find_transaction_capability_findings(root, registry=_registry())

    assert any(
        "target_not_implemented transaction requires gap_issue" in finding.detail
        for finding in findings
    )
    assert any(
        "target_not_implemented lifecycle requires gap_issues" in finding.detail
        for finding in findings
    )


def test_catalog_guard_rejects_missing_documentation_anchor(tmp_path: Path) -> None:
    root = _write_repo(tmp_path, _catalog())
    wiki = root / "wiki" / "Transaction-and-Product-Lifecycle-Capabilities.md"
    wiki.write_text("untracked prose\n", encoding="utf-8")

    findings = guard.find_transaction_capability_findings(root, registry=_registry())

    assert any("missing catalog reference" in finding.detail for finding in findings)


def test_catalog_guard_rejects_stale_generator_command(tmp_path: Path) -> None:
    payload = _catalog()
    payload["generator_command"] = "python scripts/generators/legacy_catalog.py"
    root = _write_repo(tmp_path, payload)

    findings = guard.find_transaction_capability_findings(root, registry=_registry())

    assert any("generator_command mismatch" in finding.detail for finding in findings)
