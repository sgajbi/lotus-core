"""Mutation-style tests for calculated financial-output policy governance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts.quality.calculated_output_policy_guard import evaluate, main


def _write_policy(
    root: Path,
    *,
    constant: str = "TEST_LEDGER_OUTPUT_V1",
    used: bool = True,
    lineage_bound: bool = True,
    unbound_consumer: bool = False,
) -> None:
    source = root / "src" / "owner"
    source.mkdir(parents=True, exist_ok=True)
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
            "from decimal import Decimal",
            "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1",
            "policy = TEST_LEDGER_OUTPUT_V1",
            "value = policy.normalize(Decimal('1'), field_name='value')",
        ]
        if lineage_bound:
            consumer_lines.append("identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()")
        (source / "consumer.py").write_text(
            "\n".join(consumer_lines) + "\n",
            encoding="utf-8",
        )
    if unbound_consumer:
        (source / "unbound_consumer.py").write_text(
            "from decimal import Decimal\n"
            "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
            "value = TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
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
        "lineage_gap_paths": [],
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


ContractMutation = Callable[[dict[str, Any]], None]


def _rewrite_contract(path: Path, mutate: ContractMutation) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


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


def test_guard_does_not_treat_lineage_binding_as_execution(tmp_path: Path) -> None:
    _write_policy(tmp_path, used=False)
    source = tmp_path / "src" / "owner"
    (source / "lineage_only.py").write_text(
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "TEST_LEDGER_OUTPUT_V1: no execution consumer found" in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" not in findings


def test_guard_rejects_missing_required_lineage_binding(tmp_path: Path) -> None:
    _write_policy(tmp_path, lineage_bound=False)

    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in evaluate(
        tmp_path,
        _contract(tmp_path),
    )


def test_guard_accepts_partial_binding_with_exact_consumer_gap(tmp_path: Path) -> None:
    _write_policy(tmp_path, unbound_consumer=True)

    assert (
        evaluate(
            tmp_path,
            _contract(
                tmp_path,
                lineage_binding="partial",
                lineage_gap_paths=["src/owner/unbound_consumer.py"],
            ),
        )
        == ()
    )


def test_guard_rejects_required_binding_with_unbound_consumer(tmp_path: Path) -> None:
    _write_policy(tmp_path, unbound_consumer=True)

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/unbound_consumer.py"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_rejects_missing_and_stale_consumer_gaps(tmp_path: Path) -> None:
    _write_policy(tmp_path, unbound_consumer=True)

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_binding="partial",
            lineage_gap_paths=["src/owner/stale.py"],
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/unbound_consumer.py"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: stale lineage gap at src/owner/stale.py" in findings


def test_guard_rejects_not_exposed_binding_with_lineage_consumer(tmp_path: Path) -> None:
    _write_policy(tmp_path)

    findings = evaluate(
        tmp_path,
        _contract(tmp_path, lineage_binding="not-exposed"),
    )

    assert "TEST_LEDGER_OUTPUT_V1: not-exposed policy has a lineage binding" in findings


def test_guard_rejects_duplicate_or_unsorted_consumer_gaps(tmp_path: Path) -> None:
    _write_policy(tmp_path, lineage_bound=False)

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_binding="not-exposed",
            lineage_gap_paths=["src/owner/consumer.py", "src/owner/consumer.py"],
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1.lineage_gap_paths: must be a sorted list of unique nonblank paths"
    ) in findings


def test_guard_rejects_duplicate_contract_keys(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    contract = _contract(tmp_path)
    contract.write_text(
        '{"schema_version":"1.0.0","expected_inventory":1,"expected_inventory":1,"policies":{}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON key: expected_inventory"):
        evaluate(tmp_path, contract)


def test_guard_rejects_non_object_contract_root(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    contract.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="contract root must be an object"):
        evaluate(tmp_path, contract)


def test_guard_rejects_nonliteral_policy_declaration(tmp_path: Path) -> None:
    source = tmp_path / "src" / "owner"
    source.mkdir(parents=True)
    (source / "numeric_policy.py").write_text(
        "from portfolio_common.domain.financial.calculation_precision "
        "import CalculatedDecimalPolicy\n"
        "TEST_LEDGER_OUTPUT_V1 = CalculatedDecimalPolicy("
        "name=resolve_name(), version='1.0.0', precision=18, scale=10)\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="name must be a literal"):
        evaluate(tmp_path, _contract(tmp_path))


def test_guard_rejects_ambiguous_or_duplicate_policy_declarations(tmp_path: Path) -> None:
    source = tmp_path / "src" / "owner"
    source.mkdir(parents=True)
    (source / "ambiguous.py").write_text(
        "from portfolio_common.domain.financial.calculation_precision "
        "import CalculatedDecimalPolicy\n"
        "FIRST = SECOND = CalculatedDecimalPolicy("
        "name='test-ledger-output', version='1.0.0', precision=18, scale=10)\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must use one named assignment"):
        evaluate(tmp_path, _contract(tmp_path))

    (source / "ambiguous.py").unlink()
    _write_policy(tmp_path)
    (source / "duplicate.py").write_text(
        "from portfolio_common.domain.financial.calculation_precision "
        "import CalculatedDecimalPolicy\n"
        "TEST_LEDGER_OUTPUT_V1 = CalculatedDecimalPolicy("
        "name='duplicate', version='1.0.0', precision=18, scale=10)\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate calculated policy constant"):
        evaluate(tmp_path, _contract(tmp_path))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda root: root.pop("policies"), "contract root must contain"),
        (lambda root: root.__setitem__("schema_version", "2.0.0"), "schema_version must be 1.0.0"),
        (lambda root: root.__setitem__("policies", []), "policies must be an object"),
        (
            lambda root: root.__setitem__("expected_inventory", True),
            "expected_inventory must be an integer",
        ),
        (
            lambda root: root.__setitem__("expected_inventory", 2),
            "expected_inventory=2 does not match contract count=1",
        ),
    ],
)
def test_guard_rejects_invalid_contract_envelope(
    tmp_path: Path,
    mutation: ContractMutation,
    message: str,
) -> None:
    _write_policy(tmp_path)
    contract = _contract(tmp_path)
    _rewrite_contract(contract, mutation)

    assert any(message in finding for finding in evaluate(tmp_path, contract))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda policy: policy.pop("owner"),
            "policy keys must be",
        ),
        (
            lambda policy: policy.__setitem__("owner", " "),
            "TEST_LEDGER_OUTPUT_V1.owner: must be nonblank",
        ),
        (
            lambda policy: policy.__setitem__("lineage_binding", "optional"),
            "TEST_LEDGER_OUTPUT_V1.lineage_binding: must be one of",
        ),
    ],
)
def test_guard_rejects_invalid_policy_contract(
    tmp_path: Path,
    mutation: ContractMutation,
    message: str,
) -> None:
    _write_policy(tmp_path)
    contract = _contract(tmp_path)

    def mutate_root(root: dict[str, object]) -> None:
        policies = root["policies"]
        assert isinstance(policies, dict)
        policy = policies["TEST_LEDGER_OUTPUT_V1"]
        assert isinstance(policy, dict)
        mutation(policy)

    _rewrite_contract(contract, mutate_root)

    assert any(message in finding for finding in evaluate(tmp_path, contract))


def test_main_reports_success_and_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_policy(tmp_path)
    contract = _contract(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "calculated-output-policy-guard",
            "--repo-root",
            str(tmp_path),
            "--contract",
            str(contract),
        ],
    )

    assert main() == 0
    assert "1 policies classified" in capsys.readouterr().out

    contract_payload = json.loads(contract.read_text(encoding="utf-8"))
    contract_payload["policies"]["TEST_LEDGER_OUTPUT_V1"]["scale"] = 4
    contract.write_text(json.dumps(contract_payload), encoding="utf-8")
    assert main() == 1
    assert "TEST_LEDGER_OUTPUT_V1.scale" in capsys.readouterr().err
