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
            "from portfolio_common.domain.calculation_lineage import build_calculation_lineage",
            "from portfolio_common.domain import calculation_lineage",
            "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1",
            "policy = TEST_LEDGER_OUTPUT_V1",
            "value = policy.normalize(Decimal('1'), field_name='value')",
        ]
        if lineage_bound:
            consumer_lines.append(
                "lineage = build_calculation_lineage("
                "algorithm_id='test', algorithm_version=1, intermediate_precision=64, "
                "input_payload={}, output_payload={'value': value}, "
                "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())"
            )
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
        "lineage_gap_callsites": [],
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
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_rejects_lineage_identity_that_is_computed_but_discarded(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, lineage_bound=False)
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        consumer.read_text(encoding="utf-8")
        + "identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        + "holder.identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_accepts_lineage_identity_propagated_through_local_name(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, lineage_bound=False)
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        consumer.read_text(encoding="utf-8")
        + "identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        + "lineage_builder = build_calculation_lineage\n"
        + "lineage = lineage_builder("
        + "algorithm_id='test', algorithm_version=1, intermediate_precision=64, "
        + "input_payload={}, output_payload={'value': value}, "
        + "numeric_output_policy=identity)\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path, _contract(tmp_path)) == ()


def test_guard_rejects_unrelated_method_named_like_lineage_builder(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, lineage_bound=False)
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        consumer.read_text(encoding="utf-8")
        + "identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        + "lineage = unrelated.build_calculation_lineage("
        + "numeric_output_policy=identity)\n"
        + "other_lineage = resolve_builder().build_calculation_lineage("
        + "numeric_output_policy=identity)\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_rejects_execution_and_lineage_split_across_branches(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate(execute_output):\n"
        "    if execute_output:\n"
        "        return TEST_LEDGER_OUTPUT_V1.normalize("
        "Decimal('1'), field_name='value')\n"
        "    else:\n"
        "        return build_calculation_lineage("
        "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/consumer.py::calculate"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


@pytest.mark.parametrize(
    ("import_line", "builder"),
    [
        (
            "import portfolio_common.domain.calculation_lineage as lineage_module",
            "lineage_module.build_calculation_lineage",
        ),
        (
            "import portfolio_common",
            "portfolio_common.domain.calculation_lineage.build_calculation_lineage",
        ),
    ],
)
def test_guard_accepts_verified_qualified_lineage_builders(
    tmp_path: Path,
    import_line: str,
    builder: str,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        f"{import_line}\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate():\n"
        "    value = TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')\n"
        f"    return {builder}("
        "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path, _contract(tmp_path)) == ()


def test_guard_accepts_annotated_identity_passed_to_qualified_lineage_builder(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, lineage_bound=False)
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        consumer.read_text(encoding="utf-8")
        + "identity: object = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        + "lineage = calculation_lineage.build_calculation_lineage("
        + "numeric_output_policy=identity)\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path, _contract(tmp_path)) == ()


def test_guard_rejects_lineage_identity_overwritten_before_propagation(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, lineage_bound=False)
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        consumer.read_text(encoding="utf-8")
        + "identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        + "identity = None\n"
        + "lineage = build_calculation_lineage(numeric_output_policy=identity)\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_rejects_lineage_identity_bound_on_only_one_conditional_exit(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, lineage_bound=False)
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        consumer.read_text(encoding="utf-8")
        + "identity = None\n"
        + "if expose_lineage:\n"
        + "    identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        + "lineage = build_calculation_lineage(numeric_output_policy=identity)\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_accepts_same_lineage_identity_on_every_conditional_exit(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, lineage_bound=False)
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        consumer.read_text(encoding="utf-8")
        + "if expose_lineage:\n"
        + "    identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        + "else:\n"
        + "    identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        + "lineage = build_calculation_lineage(numeric_output_policy=identity)\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path, _contract(tmp_path)) == ()


@pytest.mark.parametrize(
    "control_flow",
    [
        ("for item in items:\n        identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"),
        (
            "for item in items:\n"
            "        identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
            "    else:\n"
            "        identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        ),
        ("while expose_lineage:\n        identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"),
        (
            "try:\n"
            "        identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
            "    except Exception as identity:\n"
            "        value = TEST_LEDGER_OUTPUT_V1.normalize("
            "Decimal('2'), field_name='value')\n"
        ),
        (
            "try:\n"
            "        identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
            "    except:\n"
            "        pass\n"
        ),
        (
            "try:\n"
            "        identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
            "    except* Exception as identity:\n"
            "        pass\n"
        ),
        (
            "match lineage_mode:\n"
            "        case 'expose' if allow_lineage:\n"
            "            identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
            "            value = TEST_LEDGER_OUTPUT_V1.normalize("
            "Decimal('2'), field_name='value')\n"
        ),
    ],
)
def test_guard_rejects_identity_missing_on_a_control_flow_exit(
    tmp_path: Path,
    control_flow: str,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate():\n"
        "    value = TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')\n"
        "    identity = None\n"
        f"    {control_flow}"
        "    return build_calculation_lineage(numeric_output_policy=identity)\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_rejects_identity_bound_only_inside_async_loop(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "async def calculate():\n"
        "    value = TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')\n"
        "    identity = None\n"
        "    async for item in items:\n"
        "        identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
        "    return build_calculation_lineage(numeric_output_policy=identity)\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


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
                lineage_gap_callsites=["src/owner/unbound_consumer.py::<module>"],
            ),
        )
        == ()
    )


def test_guard_rejects_partial_binding_without_both_consumer_states(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)

    assert (
        "TEST_LEDGER_OUTPUT_V1: partial lineage binding requires bound and unbound consumers"
        in evaluate(
            tmp_path,
            _contract(tmp_path, lineage_binding="partial"),
        )
    )


def test_guard_distinguishes_bound_and_unbound_callables_in_one_file(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def bound_calculation():\n"
        "    value = TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')\n"
        "    return build_calculation_lineage("
        "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n"
        "def unbound_calculation():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )

    required_findings = evaluate(tmp_path, _contract(tmp_path))
    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at "
        "src/owner/consumer.py::unbound_calculation"
    ) in required_findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in required_findings

    assert (
        evaluate(
            tmp_path,
            _contract(
                tmp_path,
                lineage_binding="partial",
                lineage_gap_callsites=["src/owner/consumer.py::unbound_calculation"],
            ),
        )
        == ()
    )


@pytest.mark.parametrize(
    ("import_line", "receiver"),
    [
        (
            "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1 as output_policy",
            "output_policy",
        ),
        ("import owner.numeric_policy as policies", "policies.TEST_LEDGER_OUTPUT_V1"),
        (
            "import owner.numeric_policy as policies\n"
            "output_policy = policies.TEST_LEDGER_OUTPUT_V1",
            "output_policy",
        ),
    ],
)
def test_guard_resolves_imported_and_qualified_policy_aliases(
    tmp_path: Path,
    import_line: str,
    receiver: str,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        f"{import_line}\n"
        "def calculate():\n"
        f"    return {receiver}.normalize(Decimal('1'), field_name='value')\n",
        encoding="utf-8",
    )

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_binding="not-exposed",
            lineage_gap_callsites=["src/owner/consumer.py::calculate"],
        ),
    )

    assert findings == ()


def test_guard_does_not_hide_unbound_import_alias_beside_bound_consumer(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "src" / "owner" / "alias_consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1 as output_policy\n"
        "def calculate():\n"
        "    return output_policy.normalize(Decimal('1'), field_name='value')\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/alias_consumer.py::calculate"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_does_not_hide_unbound_extracted_method_beside_bound_consumer(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "src" / "owner" / "method_alias_consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "normalize_output = TEST_LEDGER_OUTPUT_V1.normalize\n"
        "def calculate():\n"
        "    return normalize_output(Decimal('1'), field_name='value')\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at "
        "src/owner/method_alias_consumer.py::calculate"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_accepts_chained_extracted_method_with_lineage_propagation(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate():\n"
        "    normalize_output: object = TEST_LEDGER_OUTPUT_V1.normalize\n"
        "    normalize_alias = normalize_output\n"
        "    value = normalize_alias(Decimal('1'), field_name='value')\n"
        "    return build_calculation_lineage("
        "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path, _contract(tmp_path)) == ()


def test_guard_does_not_count_extracted_method_after_overwrite(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "normalize_output = TEST_LEDGER_OUTPUT_V1.normalize\n"
        "normalize_output = unrelated_normalizer\n"
        "value = normalize_output(Decimal('1'), field_name='value')\n",
        encoding="utf-8",
    )

    findings = evaluate(
        tmp_path,
        _contract(tmp_path, lineage_binding="not-exposed"),
    )

    assert "TEST_LEDGER_OUTPUT_V1: no execution consumer found" in findings
    assert not any("lineage gap" in finding for finding in findings)


def test_guard_does_not_leak_policy_alias_across_parameter_shadow(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "src" / "owner" / "shadowed_consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "policy = TEST_LEDGER_OUTPUT_V1\n"
        "def calculate(policy):\n"
        "    return policy.normalize(Decimal('1'), field_name='value')\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path, _contract(tmp_path)) == ()


def test_guard_invalidates_overwritten_policy_receiver_alias(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "policy = TEST_LEDGER_OUTPUT_V1\n"
        "policy = unrelated_policy\n"
        "value = policy.normalize(Decimal('1'), field_name='value')\n",
        encoding="utf-8",
    )

    findings = evaluate(
        tmp_path,
        _contract(tmp_path, lineage_binding="not-exposed"),
    )

    assert "TEST_LEDGER_OUTPUT_V1: no execution consumer found" in findings
    assert not any("lineage gap" in finding for finding in findings)


def test_guard_rejects_required_binding_with_unbound_consumer(tmp_path: Path) -> None:
    _write_policy(tmp_path, unbound_consumer=True)

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/unbound_consumer.py::<module>"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_rejects_missing_and_stale_consumer_gaps(tmp_path: Path) -> None:
    _write_policy(tmp_path, unbound_consumer=True)

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_binding="partial",
            lineage_gap_callsites=["src/owner/stale.py::calculate"],
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/unbound_consumer.py::<module>"
    ) in findings
    assert ("TEST_LEDGER_OUTPUT_V1: stale lineage gap at src/owner/stale.py::calculate") in findings


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
            lineage_gap_callsites=[
                "src/owner/consumer.py::<module>",
                "src/owner/consumer.py::<module>",
            ],
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1.lineage_gap_callsites: must be a sorted list of unique "
        "path::callable values"
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


def test_guard_discovers_imported_and_chained_constructor_aliases(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "src" / "owner" / "unclassified.py").write_text(
        "from portfolio_common.domain.financial import calculation_precision\n"
        "Policy = calculation_precision.CalculatedDecimalPolicy\n"
        "PolicyAlias = Policy\n"
        "UNCLASSIFIED_OUTPUT_V1 = PolicyAlias("
        "name='unclassified', version='1.0.0', precision=18, scale=10)\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert "UNCLASSIFIED_OUTPUT_V1: missing contract classification" in findings
    assert "source inventory=2 does not match expected=1" in findings


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
