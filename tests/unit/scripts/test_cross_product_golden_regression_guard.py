from __future__ import annotations

import json
from pathlib import Path

from scripts.cross_product_golden_regression_guard import validate_cross_product_golden_pack


def _current_pack_and_fixture() -> tuple[dict, dict]:
    pack = json.loads(
        Path("docs/standards/cross-product-golden-regression-pack.v1.json").read_text(
            encoding="utf-8"
        )
    )
    fixture = json.loads(Path(pack["fixture"]).read_text(encoding="utf-8"))
    return pack, fixture


def test_cross_product_golden_regression_pack_matches_current_repo_truth() -> None:
    pack, fixture = _current_pack_and_fixture()

    findings = validate_cross_product_golden_pack(pack, fixture, repo_root=Path.cwd())

    assert findings == []


def test_cross_product_golden_regression_guard_requires_all_expected_sections() -> None:
    pack, fixture = _current_pack_and_fixture()
    fixture["scenarios"][0]["expected"].pop("cash_ledger_impact")

    findings = validate_cross_product_golden_pack(pack, fixture, repo_root=Path.cwd())

    assert any("missing_expected_sections" in finding for finding in findings)


def test_cross_product_golden_regression_guard_requires_gap_links_for_partial_status() -> None:
    pack, fixture = _current_pack_and_fixture()
    fixture["scenarios"][2].pop("gap_links")

    findings = validate_cross_product_golden_pack(pack, fixture, repo_root=Path.cwd())

    assert any(finding.get("missing") == "gap_links" for finding in findings)
