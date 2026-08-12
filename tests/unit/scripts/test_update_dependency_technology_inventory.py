import json
from datetime import date
from pathlib import Path

from scripts.development import update_dependency_technology_inventory as inventory


def _policy() -> dict[str, object]:
    return {
        "approved_single_spdx_expressions": ["Apache-2.0", "MIT"],
        "classifier_mappings": {
            "License :: OSI Approved :: MIT License": "MIT",
        },
        "legacy_license_mappings": {"MIT License": "MIT"},
        "ambiguous_markers": ["License :: OSI Approved"],
    }


def test_license_classification_accepts_one_explicit_approved_expression() -> None:
    result = inventory._license_classification(
        {"license_expression": "MIT", "license": "", "classifiers": []}, _policy()
    )

    assert result["classification"] == "approved"
    assert result["normalized_expression"] == "MIT"


def test_license_classification_fails_compound_and_missing_evidence_closed() -> None:
    compound = inventory._license_classification(
        {"license_expression": "MIT OR Apache-2.0", "license": "", "classifiers": []},
        _policy(),
    )
    missing = inventory._license_classification(
        {"license_expression": "", "license": "", "classifiers": []}, _policy()
    )

    assert compound["classification"] == "review_required"
    assert compound["classification_reason"] == "compound_declared_expression"
    assert missing["classification"] == "blocked"
    assert missing["classification_reason"] == "missing_license_metadata"


def test_locked_components_uses_only_governed_manifests(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime.lock"
    tooling = tmp_path / "tooling.lock"
    runtime.write_text("demo==1.0\n", encoding="utf-8")
    tooling.write_text("demo==1.0\ntool==2.0\n", encoding="utf-8")
    monkeypatch.setattr(inventory, "ROOT", tmp_path)
    monkeypatch.setattr(
        inventory,
        "LOCKS",
        (("runtime", "linux/amd64", runtime), ("ci_build_test", "linux/amd64", tooling)),
    )
    monkeypatch.setenv("PYTHONPATH", "ambient-package-that-must-not-be-inventoried")

    locks, memberships = inventory._locked_components()

    assert len(locks) == 2
    assert memberships == {
        ("demo", "1.0"): {"runtime:linux/amd64", "ci_build_test:linux/amd64"},
        ("tool", "2.0"): {"ci_build_test:linux/amd64"},
    }


def test_locked_component_identity_is_stable_across_checkout_newlines(
    tmp_path: Path, monkeypatch
) -> None:
    lock = tmp_path / "runtime.lock"
    lock.write_bytes(b"demo==1.0\r\n")
    monkeypatch.setattr(inventory, "ROOT", tmp_path)
    monkeypatch.setattr(inventory, "LOCKS", (("runtime", "linux/amd64", lock),))

    locks, _memberships = inventory._locked_components()

    lock.write_bytes(b"demo==1.0\n")
    replayed_locks, _memberships = inventory._locked_components()
    assert locks[0]["sha256"] == replayed_locks[0]["sha256"]


def test_build_inventory_is_replay_stable_for_identical_sources(
    tmp_path: Path, monkeypatch
) -> None:
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({**_policy(), "review_cadence_days": 30}), encoding="utf-8")
    monkeypatch.setattr(inventory, "ROOT", tmp_path)
    monkeypatch.setattr(inventory, "POLICY_FILE", policy_file)
    monkeypatch.setattr(
        inventory,
        "_locked_components",
        lambda: (
            [
                {
                    "path": "runtime.lock",
                    "scope": "runtime",
                    "platform": "linux/amd64",
                    "sha256": "a" * 64,
                }
            ],
            {("demo", "1.0"): {"runtime:linux/amd64"}},
        ),
    )
    monkeypatch.setattr(inventory, "_git_commit", lambda: "b" * 40)
    monkeypatch.setattr(
        inventory,
        "_fetch_pypi",
        lambda _name, _version: {
            "info": {
                "license_expression": "MIT",
                "license": None,
                "classifiers": [],
                "project_urls": {"Source": "https://example.test/source"},
                "requires_python": ">=3.11",
                "yanked": False,
            },
            "urls": [{"upload_time_iso_8601": "2026-08-01T00:00:00Z"}],
        },
    )

    first = inventory.build_inventory(reviewed_on=date(2026, 8, 12))
    second = inventory.build_inventory(reviewed_on=date(2026, 8, 12))

    assert first == second
    assert first["summary"] == {
        "component_count": 1,
        "approved_license_count": 1,
        "blocked_or_review_required_count": 1,
        "certification_decision": "blocked",
    }
    assert first["components"][0]["supportability"] == {
        "classification": "review_required",
        "classification_reason": "upstream_support_evidence_not_governed",
        "support_model": "upstream_release_evidence_plus_lotus_internal_lifecycle",
        "release_evidence_url": "https://pypi.org/project/demo/1.0/",
        "upstream_support_policy_url": None,
        "vulnerability_disclosure_url": None,
        "reviewed_on": "2026-08-12",
        "next_review_due": "2026-09-11",
        "eol_evidence_url": None,
        "approval_inference": "none",
    }
