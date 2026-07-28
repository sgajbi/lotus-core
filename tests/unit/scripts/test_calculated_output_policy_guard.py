"""Mutation-style tests for calculated financial-output policy governance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality.calculated_output_policy_guard import evaluate


def _write_policy(
    root: Path,
    *,
    constant: str = "TEST_LEDGER_OUTPUT_V1",
    used: bool = True,
    lineage_bound: bool = True,
) -> None:
    source = root / "src" / "owner"
    source.mkdir(parents=True)
    policy = source / "numeric_policy.py"
    policy.write_text(
        "from portfolio_common.domain.financial.calculation_precision "
        "import CalculatedDecimalPolicy\n"
        f"{constant} = CalculatedDecimalPolicy(\n"
        "    name='test-ledger-output', version='1.0.0', precision=18, scale=10\n"
        ")\n",
        encoding="utf-8",
    )
    if used:
        consumer_lines = [
            "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1",
            "value = TEST_LEDGER_OUTPUT_V1.normalize",
        ]
        if lineage_bound:
            consumer_lines.append("identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()")
        (source / "consumer.py").write_text(
            "\n".join(consumer_lines) + "\n",
            encoding="utf-8",
        )


def _contract(root: Path, **overrides: object) -> Path:
    policy: dict[str, object] = {
        "declaration_path": "src/owner/numeric_policy.py",
        "owner": "test-owner",
        "output_family": "test-output",
        "name": "test-ledger-output",
        "version": "1.0.0",
        "precision": 18,
        "scale": 10,
        "working_precision": 64,
        "rounding": "ROUND_HALF_EVEN",
        "lineage_binding": "required",
    }
    policy.update(overrides)
    path = root / "contract.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "expected_inventory": 1,
                "policies": {"TEST_LEDGER_OUTPUT_V1": policy},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_repository_calculated_output_policy_inventory_is_complete() -> None:
    root = Path(__file__).resolve().parents[3]

    assert (
        evaluate(
            root,
            root / "docs/standards/financial-calculated-output-policies.v1.json",
        )
        == ()
    )


def test_guard_accepts_exact_used_and_lineage_bound_policy(tmp_path: Path) -> None:
    _write_policy(tmp_path)

    assert evaluate(tmp_path, _contract(tmp_path)) == ()


def test_guard_rejects_source_shape_drift(tmp_path: Path) -> None:
    _write_policy(tmp_path)

    assert "TEST_LEDGER_OUTPUT_V1.scale: contract=4, source=10" in evaluate(
        tmp_path,
        _contract(tmp_path, scale=4),
    )


def test_guard_rejects_unclassified_and_stale_policies(tmp_path: Path) -> None:
    _write_policy(tmp_path, constant="UNCLASSIFIED_LEDGER_OUTPUT_V1")

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "UNCLASSIFIED_LEDGER_OUTPUT_V1: missing contract classification" in findings
    assert "TEST_LEDGER_OUTPUT_V1: stale contract classification" in findings


def test_guard_rejects_unused_policy(tmp_path: Path) -> None:
    _write_policy(tmp_path, used=False)

    assert "TEST_LEDGER_OUTPUT_V1: no execution consumer found" in evaluate(
        tmp_path,
        _contract(tmp_path),
    )


def test_guard_rejects_missing_required_lineage_binding(tmp_path: Path) -> None:
    _write_policy(tmp_path, lineage_bound=False)

    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding not found" in evaluate(
        tmp_path,
        _contract(tmp_path),
    )


def test_guard_rejects_duplicate_contract_keys(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    contract = _contract(tmp_path)
    contract.write_text(
        '{"schema_version":"1.0.0","expected_inventory":1,"expected_inventory":1,"policies":{}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON key: expected_inventory"):
        evaluate(tmp_path, contract)
