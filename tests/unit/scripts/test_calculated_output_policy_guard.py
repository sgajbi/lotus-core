"""Mutation-style tests for calculated financial-output policy governance."""

from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from scripts.quality.calculated_output_policy_guard import (
    _call_graph,
    _source_module,
    evaluate,
    main,
)


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


def _authored_boundary_fixture(root: Path) -> Path:
    _write_policy(root, used=False)
    (root / "src/owner/shared.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "def calculate_upstream():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n"
        "def calculate_bound():\n"
        "    value = calculate_upstream()\n"
        "    return build_calculation_lineage(algorithm_id='test', algorithm_version=1, "
        "intermediate_precision=64, input_payload={}, output_payload={'value': value}, "
        "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n",
        encoding="utf-8",
    )
    boundary = "src/owner/shared.py::calculate_bound"
    return _contract(
        root,
        lineage_boundary_callsites=[boundary],
        lineage_boundary_covered_callsites={boundary: ["src/owner/shared.py::calculate_upstream"]},
    )


@pytest.mark.parametrize("scan_pass", ["declaration", "usage", "caller-graph"])
def test_guard_excludes_generated_packaging_inputs_from_every_pass(
    tmp_path: Path, scan_pass: str
) -> None:
    contract = _authored_boundary_fixture(tmp_path)
    assert evaluate(tmp_path, contract) == ()
    generated = tmp_path / "src/owner/build/lib/owner/generated.py"
    generated.parent.mkdir(parents=True)
    content = {
        "declaration": "from portfolio_common.domain.financial.calculation_precision "
        "import CalculatedDecimalPolicy\n"
        "GENERATED_OUTPUT_V1 = CalculatedDecimalPolicy(name='generated', "
        "version='1.0.0', precision=18, scale=10)\n",
        "usage": "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "value = TEST_LEDGER_OUTPUT_V1.normalize(Decimal('3'), field_name='value')\n",
        "caller-graph": "from owner.shared import calculate_upstream\n"
        "def copied_unbound_caller():\n"
        "    return calculate_upstream()\n",
    }[scan_pass]
    generated.write_text(content, encoding="utf-8")

    assert evaluate(tmp_path, contract) == ()
    assert generated.read_text(encoding="utf-8") == content


@pytest.mark.parametrize("path", ["fresh.py", "build.py", "buildings/fresh.py"])
def test_guard_keeps_untracked_authored_callers_visible(tmp_path: Path, path: str) -> None:
    contract = _authored_boundary_fixture(tmp_path)
    source = tmp_path / "src/owner" / path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "from owner.shared import calculate_upstream\n"
        "def new_unbound_caller():\n"
        "    return calculate_upstream()\n",
        encoding="utf-8",
    )

    assert any("caller path outside" in finding for finding in evaluate(tmp_path, contract))


def test_guard_keeps_untracked_authored_cross_module_cycles_visible(tmp_path: Path) -> None:
    contract = _authored_boundary_fixture(tmp_path)
    (tmp_path / "src/owner/fresh.py").write_text(
        "from owner.shared import calculate_upstream\n"
        "def recursive_unbound_caller():\n"
        "    return recursive_unbound_caller() + calculate_upstream()\n",
        encoding="utf-8",
    )

    assert any("caller path outside" in finding for finding in evaluate(tmp_path, contract))


def test_guard_rejects_empty_authored_inventory_with_only_generated_inputs(
    tmp_path: Path,
) -> None:
    generated = tmp_path / "src/owner/build/lib/empty.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("", encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps({"schema_version": "1.0.0", "expected_inventory": 0, "policies": {}}),
        encoding="utf-8",
    )

    assert "no authored Python sources found below src/" in evaluate(tmp_path, contract)


def _retained_verification_fixture(root: Path) -> tuple[Path, Path]:
    _write_policy(root)
    source = root / "src" / "owner" / "retained.py"
    source.write_text(
        "from portfolio_common.domain.calculation_lineage import "
        "calculation_lineage_from_payload as decode, calculation_lineage_binds_output as binds\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1 as policy\n"
        "def canonical(output):\n"
        "    return {'value': policy.normalize(output['value'], field_name='value')}\n"
        "def amount(output):\n"
        "    return policy.normalize(output['value'], field_name='value')\n"
        "def verify(receipt_payload, ledger_output):\n"
        "    receipt = decode(receipt_payload)\n"
        "    if (receipt is None or receipt.algorithm_id != 'test-retained'\n"
        "        or receipt.algorithm_version != 1\n"
        "        or receipt.intermediate_precision != policy.working_precision\n"
        "        or receipt.numeric_output_policy != policy.lineage_identity()\n"
        "        or not binds(receipt, output_payload=canonical(ledger_output))):\n"
        "        raise ValueError('unavailable')\n"
        "    return amount(ledger_output)\n",
        encoding="utf-8",
    )
    boundary = "src/owner/retained.py::verify"
    contract = _contract(
        root,
        lineage_boundary_callsites=[boundary],
        lineage_boundary_covered_callsites={
            boundary: ["src/owner/retained.py::amount", "src/owner/retained.py::canonical"]
        },
        lineage_verification_boundaries={
            boundary: {
                "receipt_parameter": "receipt_payload",
                "output_parameter": "ledger_output",
                "output_canonicalizer": "src/owner/retained.py::canonical",
                "algorithm_id": "test-retained",
                "algorithm_version": 1,
            }
        },
    )
    return source, contract


def test_retained_verification_accepts_strict_import_resolved_predicate(tmp_path: Path):
    source, contract = _retained_verification_fixture(tmp_path)
    assert source.exists()
    assert evaluate(tmp_path, contract) == ()


def test_retained_verification_accepts_qualified_shared_import(tmp_path):
    source, contract = _retained_verification_fixture(tmp_path)
    text = source.read_text(encoding="utf-8")
    text = text.replace(
        "from portfolio_common.domain.calculation_lineage import "
        "calculation_lineage_from_payload as decode, calculation_lineage_binds_output as binds",
        "import portfolio_common.domain.calculation_lineage as lineage",
    ).replace(
        "decode(receipt_payload)", "lineage.calculation_lineage_from_payload(receipt_payload)"
    )
    text = text.replace("binds(receipt,", "lineage.calculation_lineage_binds_output(receipt,")
    source.write_text(text, encoding="utf-8")
    assert evaluate(tmp_path, contract) == ()


def test_retained_verification_rejects_exception_bypass(tmp_path):
    source, contract = _retained_verification_fixture(tmp_path)
    text = source.read_text(encoding="utf-8")
    before, body = text.split("def verify(receipt_payload, ledger_output):\n")
    source.write_text(
        before
        + "def verify(receipt_payload, ledger_output):\n    try:\n"
        + "".join("    " + line + "\n" for line in body.splitlines())
        + "    except ValueError:\n        return amount(ledger_output)\n",
        encoding="utf-8",
    )
    assert any(
        "invalid retained-verification boundary" in finding
        for finding in evaluate(tmp_path, contract)
    )


@pytest.mark.parametrize(
    "before,after",
    [
        ("receipt = decode(receipt_payload)", "receipt = decode(unrelated_receipt)"),
        ("receipt = decode(receipt_payload)", "receipt = receipt_payload"),
        ("receipt is None", "receipt is not None"),
        ("receipt.algorithm_id != 'test-retained'", "receipt.algorithm_id != 'wrong'"),
        ("receipt.algorithm_version != 1", "receipt.algorithm_version != 2"),
        ("receipt.intermediate_precision != policy.working_precision", "False"),
        ("receipt.numeric_output_policy != policy.lineage_identity()", "False"),
        (
            "receipt.numeric_output_policy != policy.lineage_identity()",
            "receipt.numeric_output_policy == policy.lineage_identity()",
        ),
        ("or not binds(receipt, output_payload=canonical(ledger_output))", "or False"),
        ("not binds(receipt,", "binds(receipt,"),
        ("binds(receipt,", "binds(unrelated_receipt,"),
        ("canonical(ledger_output))", "canonical(unrelated_output))"),
        ("raise ValueError('unavailable')", "return amount(ledger_output)"),
        (
            "return amount(ledger_output)",
            "receipt = decode(unrelated_receipt)\n    return amount(ledger_output)",
        ),
        (
            "return amount(ledger_output)",
            "ledger_output = unrelated_output\n    return amount(ledger_output)",
        ),
        (
            "receipt = decode(receipt_payload)",
            "if bypass:\n        return amount(ledger_output)\n"
            "    receipt = decode(receipt_payload)",
        ),
        (
            "or not binds(receipt, output_payload=canonical(ledger_output))",
            "or binds(receipt, output_payload=canonical(ledger_output)) is None",
        ),
        (
            "receipt = decode(receipt_payload)",
            "binds = untrusted\n    receipt = decode(receipt_payload)",
        ),
        (
            "receipt = decode(receipt_payload)",
            "policy = untrusted\n    receipt = decode(receipt_payload)",
        ),
        (
            "return amount(ledger_output)",
            "ledger_output['value'] = 99\n    return amount(ledger_output)",
        ),
        ("return amount(ledger_output)", "return amount(unrelated_output, ignored=ledger_output)"),
        (
            "return amount(ledger_output)",
            "result = mutate([ledger_output])\n    return amount(ledger_output)",
        ),
        (
            "return amount(ledger_output)",
            "result = receipt.numeric_output_policy.mutate()\n    return amount(ledger_output)",
        ),
        (
            "def verify(receipt_payload, ledger_output):",
            "def verify(receipt_payload, ledger_output, decode=None):",
        ),
        (
            "def verify(receipt_payload, ledger_output):",
            "def verify(receipt_payload, ledger_output, *binds):",
        ),
        (
            "def verify(receipt_payload, ledger_output):",
            "def verify(receipt_payload, ledger_output, **policy):",
        ),
        (
            "def verify(receipt_payload, ledger_output):",
            "@untrusted\ndef verify(receipt_payload, ledger_output):",
        ),
        (
            "return amount(ledger_output)",
            "another = decode(receipt_payload)\n    return amount(ledger_output)",
        ),
        (
            "or not binds(receipt, output_payload=canonical(ledger_output))",
            "or (not binds(receipt, output_payload=canonical(ledger_output)) and bypass)",
        ),
        (
            "or not binds(receipt, output_payload=canonical(ledger_output))",
            "or False\n        or "
            "(binds(receipt, output_payload=canonical(ledger_output)) and False)",
        ),
        (
            "return amount(ledger_output)",
            "ignored = (ledger_output := unrelated_output)\n    return amount(ledger_output)",
        ),
        ("return amount(ledger_output)", "return amount(unrelated_output)"),
    ],
)
def test_retained_verification_rejects_unbound_or_bypassed_predicate(tmp_path, before, after):
    source, contract = _retained_verification_fixture(tmp_path)
    text = source.read_text(encoding="utf-8")
    assert before in text
    source.write_text(text.replace(before, after), encoding="utf-8")
    findings = evaluate(tmp_path, contract)
    assert any("invalid retained-verification boundary" in finding for finding in findings)
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


@pytest.mark.parametrize("name", ["decode", "binds", "policy"])
def test_retained_verification_rejects_module_import_shadowing(tmp_path, name):
    source, contract = _retained_verification_fixture(tmp_path)
    source.write_text(
        source.read_text(encoding="utf-8") + f"\n{name} = untrusted\n", encoding="utf-8"
    )
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


def test_retained_verification_rejects_discarded_binding_result(tmp_path):
    source, contract = _retained_verification_fixture(tmp_path)
    text = (
        source.read_text(encoding="utf-8")
        .replace("or not binds(receipt, output_payload=canonical(ledger_output))", "or False")
        .replace(
            "    return amount(ledger_output)",
            "    discarded = binds(receipt, output_payload=canonical(ledger_output))\n"
            "    return amount(ledger_output)",
        )
    )
    source.write_text(text, encoding="utf-8")
    findings = evaluate(tmp_path, contract)
    assert any("invalid retained-verification boundary" in item for item in findings)
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


@pytest.mark.parametrize(
    "field,value",
    [
        ("receipt_parameter", "unrelated_receipt"),
        ("output_parameter", "unrelated_output"),
        ("output_canonicalizer", "src/owner/missing.py::canonical"),
        ("algorithm_id", "wrong"),
        ("algorithm_id", ""),
        ("algorithm_version", 2),
        ("algorithm_version", True),
        ("algorithm_version", 0),
        ("extra", "not-supported"),
    ],
)
def test_retained_verification_rejects_stale_or_malformed_specification(tmp_path, field, value):
    _, contract = _retained_verification_fixture(tmp_path)

    def mutate(payload):
        payload["policies"]["TEST_LEDGER_OUTPUT_V1"]["lineage_verification_boundaries"][
            "src/owner/retained.py::verify"
        ][field] = value

    _rewrite_contract(contract, mutate)
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


@pytest.mark.parametrize(
    "shared_name", ["calculation_lineage_from_payload", "calculation_lineage_binds_output"]
)
def test_retained_verification_rejects_untrusted_import(tmp_path, shared_name):
    source, contract = _retained_verification_fixture(tmp_path)
    alias = "decode" if shared_name.endswith("from_payload") else "binds"
    source.write_text(
        source.read_text(encoding="utf-8") + f"\nfrom untrusted import {shared_name} as {alias}\n",
        encoding="utf-8",
    )
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


def test_retained_verification_cannot_use_arbitrary_terminal(tmp_path):
    _, contract = _retained_verification_fixture(tmp_path)
    boundary = "src/owner/retained.py::verify"
    _rewrite_contract(
        contract,
        lambda payload: payload["policies"]["TEST_LEDGER_OUTPUT_V1"].update(
            lineage_boundary_terminal_callsites={
                boundary: {boundary: "read-only-lineage-verification"}
            }
        ),
    )
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


def test_retained_verification_rejects_mutated_precomputed_canonical_output(tmp_path):
    source, contract = _retained_verification_fixture(tmp_path)
    text = (
        source.read_text(encoding="utf-8")
        .replace(
            "    receipt = decode(receipt_payload)",
            "    payload = canonical(ledger_output)\n"
            "    changed = mutate(payload)\n    receipt = decode(receipt_payload)",
        )
        .replace("output_payload=canonical(ledger_output)", "output_payload=payload")
    )
    source.write_text(text, encoding="utf-8")
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


def _execute_retained_fixture(source: str, *, bound: str, output: str):
    """Execute only authored fixture functions to demonstrate a guard counterexample."""
    policy = SimpleNamespace(
        working_precision=64,
        lineage_identity=lambda: "same-policy",
        normalize=lambda value, **kwargs: Decimal(str(value)),
    )
    receipt = SimpleNamespace(
        algorithm_id="test-retained",
        algorithm_version=1,
        intermediate_precision=64,
        numeric_output_policy="same-policy",
        value=Decimal(bound),
    )

    def mutate(alias):
        retained = alias["retained"] if isinstance(alias, dict) else alias[0]
        retained["value"] = Decimal("99")

    namespace = {
        "policy": policy,
        "decode": lambda payload: payload,
        "binds": lambda receipt, *, output_payload: receipt.value == output_payload["value"],
        "mutate": mutate,
    }
    tree = ast.parse(source)
    functions = ast.Module(
        body=[node for node in tree.body if isinstance(node, ast.FunctionDef)], type_ignores=[]
    )
    exec(compile(functions, "<authored-retained-fixture>", "exec"), namespace)
    return namespace["verify"](receipt, {"value": Decimal(output)})


@pytest.mark.parametrize("container", ["{'retained': ledger_output}", "[ledger_output]"])
def test_retained_verification_rejects_executed_container_alias_escape(tmp_path, container):
    source, contract = _retained_verification_fixture(tmp_path)
    original = source.read_text(encoding="utf-8")
    assert _execute_retained_fixture(original, bound="1", output="1") == Decimal("1")
    mutated = original.replace(
        "    return amount(ledger_output)",
        f"    shadow = {container}\n    changed = mutate(shadow)\n    return amount(ledger_output)",
    )
    assert _execute_retained_fixture(mutated, bound="1", output="1") == Decimal("99")
    source.write_text(mutated, encoding="utf-8")
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


def test_retained_verification_rejects_executed_constant_canonical_projection(tmp_path):
    source, contract = _retained_verification_fixture(tmp_path)
    original = source.read_text(encoding="utf-8")
    assert _execute_retained_fixture(original, bound="1", output="1") == Decimal("1")
    mutated = original.replace("policy.normalize(output['value'],", "policy.normalize('0',", 1)
    assert _execute_retained_fixture(mutated, bound="0", output="99") == Decimal("99")
    source.write_text(mutated, encoding="utf-8")
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


@pytest.mark.parametrize(
    "projection",
    [
        "{'value': policy.normalize('0', field_name='value')}",
        "{'wrong': policy.normalize(output['value'], field_name='wrong')}",
        "{'value': policy.normalize(output['other'], field_name='value')}",
        "{'value': policy.normalize(output['value'] * 0, field_name='value')}",
        "{'value': policy.normalize(output['value'], field_name='value'), "
        "'extra': policy.normalize('0', field_name='extra')}",
    ],
)
def test_retained_verification_rejects_fabricated_or_remapped_field_projection(
    tmp_path, projection
):
    source, contract = _retained_verification_fixture(tmp_path)
    text = source.read_text(encoding="utf-8").replace(
        "{'value': policy.normalize(output['value'], field_name='value')}", projection
    )
    source.write_text(text, encoding="utf-8")
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


@pytest.mark.parametrize(
    "hidden_alias",
    [
        "(ledger_output,)",
        "{'receipt': receipt}",
        "{'output': canonical(ledger_output)}",
        "lambda: ledger_output",
        "ledger_output['value']",
    ],
)
def test_retained_verification_rejects_unsupported_alias_bearing_assignment(tmp_path, hidden_alias):
    source, contract = _retained_verification_fixture(tmp_path)
    text = source.read_text(encoding="utf-8").replace(
        "    return amount(ledger_output)",
        f"    shadow = {hidden_alias}\n    return amount(ledger_output)",
    )
    source.write_text(text, encoding="utf-8")
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


def _complete_projection_fixture(root: Path) -> tuple[Path, Path]:
    source, contract = _retained_verification_fixture(root)
    text = source.read_text(encoding="utf-8")
    start, remainder = text.split("def canonical(output):\n")
    _, tail = remainder.split("def amount(output):\n")
    projection = (
        "def canonical(output):\n"
        "    owned_policy = source_policy\n"
        "    quantum = D(1).scaleb(-owned_policy.scale)\n"
        "    projected: dict[str, object] = {}\n"
        "    for key, value in output.items():\n"
        "        if value is None:\n            continue\n"
        "        if isinstance(value, D):\n"
        "            with owned_policy.arithmetic_context():\n"
        "                value = owned_policy.normalize(value, field_name=key).quantize(\n"
        "                    quantum, rounding=owned_policy.rounding)\n"
        "        projected[key] = value\n"
        "    return projected\n"
    )
    source.write_text(
        start + "from decimal import Decimal as D\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1 as source_policy\n"
        + projection
        + "def amount(output):\n"
        + tail,
        encoding="utf-8",
    )
    return source, contract


def test_retained_verification_accepts_alpha_renamed_complete_projection(tmp_path):
    _, contract = _complete_projection_fixture(tmp_path)
    assert evaluate(tmp_path, contract) == ()


def test_retained_verification_rejects_alias_hidden_by_covered_helper(tmp_path):
    source, contract = _retained_verification_fixture(tmp_path)
    text = (
        source.read_text(encoding="utf-8")
        .replace(
            "    return policy.normalize(output['value'], field_name='value')",
            "    ignored = policy.normalize(output['value'], field_name='value')\n"
            "    return output",
        )
        .replace(
            "    return amount(ledger_output)",
            "    shadow = amount(ledger_output)\n"
            "    changed = shadow.update(value=99)\n    return amount(ledger_output)",
        )
    )
    source.write_text(text, encoding="utf-8")
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


@pytest.mark.parametrize(
    "body",
    [
        "    return policy.normalize(output.pop('value'), field_name='value')\n",
        "    scalar = policy.normalize(output['value'], field_name='value')\n"
        "    return scalar if bypass else output\n",
        "    if bypass:\n"
        "        output = policy.normalize(output['value'], field_name='value')\n"
        "    return output\n",
        "    scalar = policy.normalize(output['value'], field_name='value')\n"
        "    output.update(value=99)\n    return scalar\n",
        "    scalar = policy.normalize(output['value'], field_name='value')\n"
        "    return unrelated(scalar)\n",
        "    scalar = policy.normalize(output['value'], field_name='value')\n"
        "    return output.get('value')\n",
        "    scalar = policy.normalize(output['value'], field_name='value')\n"
        "    scalar = output\n    return scalar\n",
    ],
)
def test_retained_verification_rejects_mutable_or_opaque_amount_helpers(tmp_path, body):
    source, contract = _retained_verification_fixture(tmp_path)
    text = source.read_text(encoding="utf-8")
    prefix, remainder = text.split("def amount(output):\n")
    _, verifier = remainder.split("def verify(receipt_payload, ledger_output):\n")
    source.write_text(
        prefix
        + "def amount(output):\n"
        + body
        + "def verify(receipt_payload, ledger_output):\n"
        + verifier,
        encoding="utf-8",
    )
    findings = evaluate(tmp_path, contract)
    assert any("invalid retained-verification boundary" in item for item in findings)
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_retained_verification_accepts_readonly_conditional_scalar_helper(tmp_path):
    source, contract = _retained_verification_fixture(tmp_path)
    text = source.read_text(encoding="utf-8").replace(
        "    return policy.normalize(output['value'], field_name='value')",
        "    if output.get('value') is None:\n        return None\n"
        "    numeric_policy = policy\n"
        "    scalar = numeric_policy.normalize(output['value'], field_name='value')\n"
        "    return scalar if scalar == output.get('value') else None",
    )
    source.write_text(text, encoding="utf-8")
    assert evaluate(tmp_path, contract) == ()


@pytest.mark.parametrize(
    "before,after",
    [
        (
            "owned_policy.normalize(value, field_name=key)",
            "owned_policy.normalize('0', field_name=key)",
        ),
        ("projected[key] = value", "projected['wrong'] = value"),
        ("output.items()", "unrelated_output.items()"),
        ("if value is None", "if value is not None"),
        ("rounding=owned_policy.rounding", "rounding='ROUND_DOWN'"),
        ("    return projected", "    return {'value': D(0)}"),
        ("def canonical(output):", "def canonical(output, D=None):"),
        ("quantum", "isinstance"),
    ],
)
def test_retained_verification_rejects_drifting_complete_projection(tmp_path, before, after):
    source, contract = _complete_projection_fixture(tmp_path)
    text = source.read_text(encoding="utf-8")
    assert before in text
    source.write_text(text.replace(before, after), encoding="utf-8")
    assert any(
        "invalid retained-verification boundary" in item for item in evaluate(tmp_path, contract)
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "stale", "unbound_caller"])
def test_retained_verification_registration_is_not_an_allowlist(tmp_path, mutation):
    source, contract = _retained_verification_fixture(tmp_path)
    boundary = "src/owner/retained.py::verify"
    if mutation == "missing":
        _rewrite_contract(
            contract,
            lambda payload: payload["policies"]["TEST_LEDGER_OUTPUT_V1"].pop(
                "lineage_verification_boundaries"
            ),
        )
    elif mutation == "duplicate":
        _rewrite_contract(
            contract,
            lambda payload: payload["policies"]["TEST_LEDGER_OUTPUT_V1"][
                "lineage_boundary_covered_callsites"
            ][boundary].append("src/owner/retained.py::canonical"),
        )
    elif mutation == "stale":
        _rewrite_contract(
            contract,
            lambda payload: payload["policies"]["TEST_LEDGER_OUTPUT_V1"][
                "lineage_boundary_covered_callsites"
            ][boundary].append("src/owner/missing.py::canonical"),
        )
    else:
        (source.parent / "unbound.py").write_text(
            "from owner.retained import canonical\n"
            "def escape(output):\n    return canonical(output)\n",
            encoding="utf-8",
        )
    assert evaluate(tmp_path, contract)

@pytest.mark.parametrize(
    "suffix",
    [
        "\ndef harmless(value: Mapping[str, Decimal | None], *, ready: bool = True) -> tuple[Decimal | None, ...]:\n    return ()\n",
        "\nfrom decimal import Decimal as Amount\ndef harmless(value: Amount | None = None) -> FxSourceEvidenceConfirmation:\n    return None\n",
        "\nimport decimal as amounts\ndef harmless(value: amounts.Decimal | None = None) -> tuple[FxCurrencyBasis, ...]:\n    return ()\n",
    ],
)
def test_retained_owner_accepts_supported_resolved_inert_headers(tmp_path, suffix):
    retained, _, contract = _typed_original_presence_fixture(tmp_path)
    retained.write_text(retained.read_text(encoding="utf-8") + suffix, encoding="utf-8")
    assert evaluate(tmp_path, contract) == ()


@pytest.mark.parametrize(
    "header",
    [
        "def unrelated(default=EFFECT):\n    pass\n",
        "def unrelated(*, default=EFFECT):\n    pass\n",
        "def unrelated(value: EFFECT):\n    pass\n",
        "def unrelated() -> EFFECT:\n    pass\n",
        "@(EFFECT or (lambda fn: fn))\ndef unrelated():\n    pass\n",
        "def unrelated(*values: EFFECT):\n    pass\n",
        "def unrelated(**values: EFFECT):\n    pass\n",
    ],
)
def test_retained_owner_refuses_executed_unrelated_header_rebinding(tmp_path, header):
    retained, _, contract = _typed_original_presence_fixture(tmp_path)
    assert evaluate(tmp_path, contract) == ()
    effect = "globals().__setitem__('retained_fx_output_payload', lambda output: {})"
    header = header.replace("EFFECT", effect)
    namespace = {"retained_fx_output_payload": lambda output: dict(output)}
    assert namespace["retained_fx_output_payload"]({"amount": Decimal("42")})
    exec(compile(header, "<retained-header-effect-control>", "exec", dont_inherit=True), namespace)
    assert namespace["retained_fx_output_payload"]({"amount": Decimal("42")}) == {}
    retained.write_text(retained.read_text(encoding="utf-8") + "\n" + header, encoding="utf-8")
    assert evaluate(tmp_path, contract)


@pytest.mark.parametrize(
    "suffix",
    [
        "\ndict = 'not-a-type'\ndef unrelated(value: dict):\n    pass\n",
        "\nMapping = 'not-a-type'\ndef unrelated(value: Mapping[str, object]):\n    pass\n",
        "\nfrom pathlib import Path\ndef unrelated(value: Path):\n    pass\n",
        "\ndef unrelated(value: (lambda: object)()):\n    pass\n",
    ],
)
def test_retained_owner_refuses_unproven_type_bindings(tmp_path, suffix):
    retained, _, contract = _typed_original_presence_fixture(tmp_path)
    retained.write_text(retained.read_text(encoding="utf-8") + suffix, encoding="utf-8")
    assert evaluate(tmp_path, contract)


def test_retained_owner_refuses_header_effect_in_module_control_block(tmp_path):
    retained, _, contract = _typed_original_presence_fixture(tmp_path)
    source = retained.read_text(encoding="utf-8")
    source += (
        "\nif True:\n"
        "    def unrelated(default=globals().__setitem__('retained_fx_output_payload', "
        "lambda output: {})):\n"
        "        pass\n"
    )
    retained.write_text(source, encoding="utf-8")
    assert evaluate(tmp_path, contract)


@pytest.mark.parametrize(
    ("source_path", "module"),
    [
        ("src/owner/numeric_policy.py", "owner.numeric_policy"),
        (
            "src/libs/portfolio-common/portfolio_common/domain/numeric_policy.py",
            "portfolio_common.domain.numeric_policy",
        ),
        (
            "src/services/portfolio_service/app/domain/numeric_policy.py",
            "app.domain.numeric_policy",
        ),
    ],
)
def test_guard_derives_importable_policy_module(
    source_path: str,
    module: str,
) -> None:
    assert _source_module(source_path) == module


@pytest.mark.parametrize("source_path", ["numeric_policy.py", "src"])
def test_guard_rejects_non_module_policy_paths(source_path: str) -> None:
    with pytest.raises(ValueError, match="calculated policy path"):
        _source_module(source_path)


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
    "expression",
    [
        (
            "TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value') "
            "if execute_output else build_calculation_lineage("
            "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())"
        ),
        (
            "TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value') "
            "or build_calculation_lineage("
            "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())"
        ),
    ],
)
def test_guard_rejects_execution_and_lineage_split_across_expression_exits(
    tmp_path: Path,
    expression: str,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate(execute_output):\n"
        f"    return {expression}\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/consumer.py::calculate"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_propagates_predicate_execution_to_every_exit(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate():\n"
        "    if (value := TEST_LEDGER_OUTPUT_V1.normalize("
        "Decimal('1'), field_name='value')):\n"
        "        return build_calculation_lineage("
        "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n"
        "    return value\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/consumer.py::calculate"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


@pytest.mark.parametrize(
    "body",
    [
        (
            "    return TEST_LEDGER_OUTPUT_V1.normalize("
            "Decimal('1'), field_name='value')\n"
            "    return build_calculation_lineage("
            "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n"
        ),
        (
            "    if return_output:\n"
            "        return TEST_LEDGER_OUTPUT_V1.normalize("
            "Decimal('1'), field_name='value')\n"
            "        return build_calculation_lineage("
            "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n"
            "    return None\n"
        ),
    ],
)
def test_guard_ignores_unreachable_lineage_after_terminal_statement(
    tmp_path: Path,
    body: str,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate(return_output=True):\n"
        f"{body}",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/consumer.py::calculate"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


@pytest.mark.parametrize(
    "signature",
    [
        "policy=TEST_LEDGER_OUTPUT_V1",
        "*, policy=TEST_LEDGER_OUTPUT_V1",
    ],
)
def test_guard_resolves_policy_parameter_defaults(
    tmp_path: Path,
    signature: str,
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "src" / "owner" / "default_consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        f"def calculate({signature}):\n"
        "    return policy.normalize(Decimal('1'), field_name='value')\n",
        encoding="utf-8",
    )

    findings = evaluate(tmp_path, _contract(tmp_path))

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at "
        "src/owner/default_consumer.py::calculate"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_rejects_exceptional_exit_between_execution_and_lineage(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate():\n"
        "    try:\n"
        "        value = TEST_LEDGER_OUTPUT_V1.normalize("
        "Decimal('1'), field_name='value')\n"
        "        fallible_operation()\n"
        "        return build_calculation_lineage("
        "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n"
        "    except Exception:\n"
        "        return value\n",
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
            "        value = TEST_LEDGER_OUTPUT_V1.normalize("
            "Decimal('2'), field_name='value')\n"
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
        (
            "match lineage_mode:\n"
            "        case 'expose':\n"
            "            identity = TEST_LEDGER_OUTPUT_V1.lineage_identity()\n"
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


def test_guard_accepts_verified_final_output_boundary_for_upstream_arithmetic(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, unbound_consumer=True)
    (tmp_path / "src" / "owner" / "unbound_consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate_upstream():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        "from owner.unbound_consumer import calculate_upstream\n"
        + consumer.read_text(encoding="utf-8")
        + "upstream = calculate_upstream()\n",
        encoding="utf-8",
    )

    boundary = "src/owner/consumer.py::<module>"
    upstream = "src/owner/unbound_consumer.py::calculate_upstream"

    assert (
        evaluate(
            tmp_path,
            _contract(
                tmp_path,
                lineage_boundary_callsites=[boundary],
                lineage_boundary_covered_callsites={boundary: [upstream]},
            ),
        )
        == ()
    )


def test_guard_rejects_shared_reexported_arithmetic_with_an_unbound_caller(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    source = tmp_path / "src" / "owner"
    (source / "shared.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate_upstream():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )
    nested = source / "calculation"
    nested.mkdir()
    (nested / "__init__.py").write_text(
        "from .shared import calculate_upstream\n",
        encoding="utf-8",
    )
    (source / "shared.py").replace(nested / "shared.py")
    (source / "consumer.py").write_text(
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.wrapper import calculate_wrapper\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate_bound():\n"
        "    value = calculate_wrapper()\n"
        "    return build_calculation_lineage(\n"
        "        algorithm_id='test', algorithm_version=1, intermediate_precision=64,\n"
        "        input_payload={}, output_payload={'value': value},\n"
        "        numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity(),\n"
        "    )\n",
        encoding="utf-8",
    )
    (source / "wrapper.py").write_text(
        "from owner.calculation import calculate_upstream\n"
        "def calculate_wrapper():\n"
        "    return calculate_upstream()\n",
        encoding="utf-8",
    )
    (source / "unbound.py").write_text(
        "from owner.wrapper import calculate_wrapper\n"
        "def calculate_unbound():\n"
        "    return calculate_wrapper()\n",
        encoding="utf-8",
    )
    boundary = "src/owner/consumer.py::calculate_bound"
    upstream = "src/owner/calculation/shared.py::calculate_upstream"
    wrapper = "src/owner/wrapper.py::calculate_wrapper"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={boundary: [upstream]},
            lineage_boundary_terminal_callsites={
                boundary: {wrapper: "lineage-bound-sibling-orchestrator"}
            },
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1: lineage boundary coverage has a caller path outside assigned "
        f"boundaries from {upstream}"
    ) in findings
    assert (
        "TEST_LEDGER_OUTPUT_V1: lineage dataflow terminal has callers and is not terminal at "
        f"{wrapper}"
    ) in findings
    assert f"TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at {upstream}" in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


def test_guard_rejects_unknown_terminal_when_boundary_has_no_coverage(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)
    boundary = "src/owner/consumer.py::<module>"
    unknown = "src/owner/missing.py::missing"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={},
            lineage_boundary_terminal_callsites={
                boundary: {unknown: "read-only-lineage-verification"}
            },
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1: lineage dataflow terminals declared for boundary without "
        f"coverage at {boundary}"
    ) in findings
    assert f"TEST_LEDGER_OUTPUT_V1: unknown lineage dataflow terminal at {unknown}" in findings


def test_guard_rejects_non_leaf_terminal_when_boundary_has_no_coverage(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path)
    source = tmp_path / "src" / "owner"
    (source / "shared.py").write_text(
        "def helper():\n    return 1\ndef wrapper():\n    return helper()\n",
        encoding="utf-8",
    )
    boundary = "src/owner/consumer.py::<module>"
    non_leaf = "src/owner/shared.py::helper"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={},
            lineage_boundary_terminal_callsites={
                boundary: {non_leaf: "lineage-bound-sibling-orchestrator"}
            },
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1: lineage dataflow terminals declared for boundary without "
        f"coverage at {boundary}"
    ) in findings
    assert (
        "TEST_LEDGER_OUTPUT_V1: lineage dataflow terminal has callers and is not terminal at "
        f"{non_leaf}"
    ) in findings


def test_exact_call_graph_resolves_self_and_cls_calls(tmp_path: Path) -> None:
    source = tmp_path / "src" / "owner"
    source.mkdir(parents=True)
    (source / "service.py").write_text(
        "class Service:\n"
        "    def helper(self):\n"
        "        return 1\n"
        "    def instance_caller(self):\n"
        "        return self.helper()\n"
        "    @classmethod\n"
        "    def class_caller(cls):\n"
        "        return cls.helper(cls)\n",
        encoding="utf-8",
    )

    graph = _call_graph(tmp_path, exact_calls_only=True)

    helper = "src/owner/service.py::Service.helper"
    assert graph[helper] == {
        "src/owner/service.py::Service.class_caller",
        "src/owner/service.py::Service.instance_caller",
    }


def test_guard_rejects_same_module_wrapper_with_external_unbound_caller(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    source = tmp_path / "src" / "owner"
    (source / "shared.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate_upstream():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n"
        "def calculate_wrapper():\n"
        "    return calculate_upstream()\n"
        "def calculate_bound():\n"
        "    value = calculate_upstream()\n"
        "    return build_calculation_lineage(\n"
        "        algorithm_id='test', algorithm_version=1, intermediate_precision=64,\n"
        "        input_payload={}, output_payload={'value': value},\n"
        "        numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity(),\n"
        "    )\n",
        encoding="utf-8",
    )
    (source / "unbound.py").write_text(
        "from owner.shared import calculate_wrapper\n"
        "def calculate_unbound():\n"
        "    return calculate_wrapper()\n",
        encoding="utf-8",
    )
    boundary = "src/owner/shared.py::calculate_bound"
    upstream = "src/owner/shared.py::calculate_upstream"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={boundary: [upstream]},
        ),
    )

    assert any("caller path outside" in finding for finding in findings)


def test_guard_rejects_protocol_dispatch_with_bound_and_unbound_callers(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, used=False)
    source = tmp_path / "src" / "owner"
    (source / "calculator.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "class Calculator:\n"
        "    def calculate(self):\n"
        "        return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )
    (source / "bound.py").write_text(
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.calculator import Calculator\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate_bound(calculator: Calculator):\n"
        "    value = calculator.calculate()\n"
        "    return build_calculation_lineage(\n"
        "        algorithm_id='test', algorithm_version=1, intermediate_precision=64,\n"
        "        input_payload={}, output_payload={'value': value},\n"
        "        numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity(),\n"
        "    )\n",
        encoding="utf-8",
    )
    (source / "unbound.py").write_text(
        "from owner.calculator import Calculator\n"
        "def calculate_unbound(calculator: Calculator):\n"
        "    return calculator.calculate()\n",
        encoding="utf-8",
    )
    boundary = "src/owner/bound.py::calculate_bound"
    upstream = "src/owner/calculator.py::Calculator.calculate"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={boundary: [upstream]},
        ),
    )

    assert any("caller path outside" in finding for finding in findings)


def test_guard_does_not_hide_unrelated_gap_beside_verified_boundary(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, unbound_consumer=True)
    (tmp_path / "src" / "owner" / "unbound_consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate_upstream():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )
    consumer = tmp_path / "src" / "owner" / "consumer.py"
    consumer.write_text(
        "from owner.unbound_consumer import calculate_upstream\n"
        + consumer.read_text(encoding="utf-8")
        + "upstream = calculate_upstream()\n",
        encoding="utf-8",
    )
    unrelated = tmp_path / "src" / "owner" / "unrelated_consumer.py"
    unrelated.write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "value = TEST_LEDGER_OUTPUT_V1.normalize(Decimal('3'), field_name='value')\n",
        encoding="utf-8",
    )
    boundary = "src/owner/consumer.py::<module>"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={
                boundary: [
                    "src/owner/unbound_consumer.py::calculate_upstream",
                    "src/owner/unrelated_consumer.py::<module>",
                ]
            },
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at "
        "src/owner/unrelated_consumer.py::<module>"
    ) in findings
    assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings
    assert any("has no call-graph path" in finding for finding in findings)


def test_guard_rejects_sibling_consumer_connected_only_by_shared_helper(
    tmp_path: Path,
) -> None:
    _write_policy(tmp_path, unbound_consumer=True)
    source = tmp_path / "src" / "owner"
    (source / "shared.py").write_text("def shared():\n    return None\n", encoding="utf-8")
    (source / "unbound_consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "from owner.shared import shared\n"
        "def unrelated_calculation():\n"
        "    shared()\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )
    consumer = source / "consumer.py"
    consumer.write_text(
        "from owner.shared import shared\n" + consumer.read_text(encoding="utf-8") + "shared()\n",
        encoding="utf-8",
    )
    boundary = "src/owner/consumer.py::<module>"
    unrelated = "src/owner/unbound_consumer.py::unrelated_calculation"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={boundary: [unrelated]},
        ),
    )

    assert any("has no call-graph path" in finding for finding in findings)
    assert f"TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at {unrelated}" in findings


def test_guard_rejects_unimported_same_named_consumer(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    source = tmp_path / "src" / "owner"
    (source / "real.py").write_text(
        "def calculate_upstream():\n    return 1\n",
        encoding="utf-8",
    )
    (source / "unrelated.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate_upstream():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )
    consumer = source / "consumer.py"
    consumer.write_text(
        "from owner.real import calculate_upstream\n"
        + consumer.read_text(encoding="utf-8")
        + "upstream = calculate_upstream()\n",
        encoding="utf-8",
    )
    boundary = "src/owner/consumer.py::<module>"
    unrelated = "src/owner/unrelated.py::calculate_upstream"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={boundary: [unrelated]},
        ),
    )

    assert any("has no call-graph path" in finding for finding in findings)
    assert f"TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at {unrelated}" in findings


def test_guard_rejects_unimported_same_name_with_dotted_import(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    source = tmp_path / "src" / "owner"
    (source / "real.py").write_text(
        "def calculate_upstream():\n    return 1\n",
        encoding="utf-8",
    )
    (source / "unrelated.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def calculate_upstream():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )
    consumer = source / "consumer.py"
    consumer.write_text(
        "import owner.real\n"
        + consumer.read_text(encoding="utf-8")
        + "upstream = owner.real.calculate_upstream()\n",
        encoding="utf-8",
    )
    boundary = "src/owner/consumer.py::<module>"
    unrelated = "src/owner/unrelated.py::calculate_upstream"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={boundary: [unrelated]},
        ),
    )

    assert any("has no call-graph path" in finding for finding in findings)
    assert f"TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at {unrelated}" in findings


def test_guard_rejects_stale_declared_boundary_coverage(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    boundary = "src/owner/consumer.py::<module>"

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=[boundary],
            lineage_boundary_covered_callsites={
                boundary: ["src/owner/missing_consumer.py::<module>"]
            },
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1: stale lineage boundary coverage at "
        "src/owner/missing_consumer.py::<module>"
    ) in findings


def test_guard_rejects_boundary_that_does_not_invoke_governed_builder(tmp_path: Path) -> None:
    _write_policy(tmp_path, unbound_consumer=True)

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_boundary_callsites=["src/owner/unbound_consumer.py::<module>"],
        ),
    )

    assert (
        "TEST_LEDGER_OUTPUT_V1: lineage boundary does not invoke the governed builder at "
        "src/owner/unbound_consumer.py::<module>"
    ) in findings


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


@pytest.mark.parametrize(
    ("local_name", "rebind_line"),
    [
        ("tracked", "from unrelated import replacement as tracked"),
        ("tracked", "import unrelated as tracked"),
        ("replacement", "from unrelated import replacement"),
        ("unrelated", "import unrelated.replacement"),
        ("tracked", "from unrelated import *"),
    ],
)
@pytest.mark.parametrize(
    "alias_kind",
    ["policy_receiver", "lineage_identity", "execution_method", "lineage_builder"],
)
def test_guard_invalidates_every_alias_kind_rebound_by_import(
    tmp_path: Path,
    local_name: str,
    rebind_line: str,
    alias_kind: str,
) -> None:
    _write_policy(tmp_path, used=False)
    setup_and_use = {
        "policy_receiver": (
            f"{local_name} = TEST_LEDGER_OUTPUT_V1",
            f"{local_name}.normalize(Decimal('1'), field_name='value')",
        ),
        "lineage_identity": (
            f"{local_name} = TEST_LEDGER_OUTPUT_V1.lineage_identity()",
            "TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')\n"
            "build_calculation_lineage("
            f"numeric_output_policy={local_name})",
        ),
        "execution_method": (
            f"{local_name} = TEST_LEDGER_OUTPUT_V1.normalize",
            f"{local_name}(Decimal('1'), field_name='value')",
        ),
        "lineage_builder": (
            f"{local_name} = build_calculation_lineage",
            "TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')\n"
            f"{local_name}("
            "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())",
        ),
    }
    setup, use = setup_and_use[alias_kind]
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from portfolio_common.domain.calculation_lineage import build_calculation_lineage\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        f"{setup}\n"
        f"{rebind_line}\n"
        f"{use}\n",
        encoding="utf-8",
    )

    findings = evaluate(
        tmp_path,
        _contract(
            tmp_path,
            lineage_binding="not-exposed"
            if alias_kind in {"policy_receiver", "execution_method"}
            else "required",
        ),
    )

    if alias_kind in {"policy_receiver", "execution_method"} or rebind_line.endswith("import *"):
        assert "TEST_LEDGER_OUTPUT_V1: no execution consumer found" in findings
        assert not any("lineage gap" in finding for finding in findings)
    else:
        assert (
            "TEST_LEDGER_OUTPUT_V1: unclassified lineage gap at src/owner/consumer.py::<module>"
        ) in findings
        assert "TEST_LEDGER_OUTPUT_V1: required lineage binding is incomplete" in findings


@pytest.mark.parametrize(
    ("recognized_import", "execution"),
    [
        (
            "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1 as rebound",
            "rebound.normalize(Decimal('1'), field_name='value')",
        ),
        (
            "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1",
            "TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')",
        ),
    ],
)
def test_guard_installs_recognized_policy_binding_after_import_invalidation(
    tmp_path: Path,
    recognized_import: str,
    execution: str,
) -> None:
    _write_policy(tmp_path, used=False)
    local_name = "rebound" if recognized_import.endswith(" as rebound") else "TEST_LEDGER_OUTPUT_V1"
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        f"{local_name} = unrelated_policy\n"
        f"{recognized_import}\n"
        f"{execution}\n",
        encoding="utf-8",
    )

    assert (
        evaluate(
            tmp_path,
            _contract(
                tmp_path,
                lineage_binding="not-exposed",
                lineage_gap_callsites=["src/owner/consumer.py::<module>"],
            ),
        )
        == ()
    )


@pytest.mark.parametrize(
    "unrelated_import",
    [
        "from unrelated import TEST_LEDGER_OUTPUT_V1",
        "from .unrelated import TEST_LEDGER_OUTPUT_V1",
        "from ...unrelated import TEST_LEDGER_OUTPUT_V1",
        "from unrelated import TEST_LEDGER_OUTPUT_V1 as rebound",
    ],
)
def test_guard_does_not_trust_policy_name_imported_from_unrelated_module(
    tmp_path: Path,
    unrelated_import: str,
) -> None:
    _write_policy(tmp_path, used=False)
    imported_name = (
        "rebound" if unrelated_import.endswith(" as rebound") else "TEST_LEDGER_OUTPUT_V1"
    )
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        "def governed_calculation():\n"
        "    return TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')\n"
        f"{unrelated_import}\n"
        "def unrelated_calculation():\n"
        f"    return {imported_name}.normalize(Decimal('2'), field_name='value')\n",
        encoding="utf-8",
    )

    assert (
        evaluate(
            tmp_path,
            _contract(
                tmp_path,
                lineage_binding="not-exposed",
                lineage_gap_callsites=[
                    "src/owner/consumer.py::governed_calculation",
                ],
            ),
        )
        == ()
    )


@pytest.mark.parametrize(
    ("recognized_import", "builder_call"),
    [
        (
            "from portfolio_common.domain.calculation_lineage "
            "import build_calculation_lineage as rebound",
            "rebound",
        ),
        (
            "from portfolio_common.domain.calculation_lineage import build_calculation_lineage",
            "build_calculation_lineage",
        ),
        (
            "import portfolio_common.domain.calculation_lineage as rebound",
            "rebound.build_calculation_lineage",
        ),
    ],
)
def test_guard_installs_recognized_lineage_builder_after_import_invalidation(
    tmp_path: Path,
    recognized_import: str,
    builder_call: str,
) -> None:
    _write_policy(tmp_path, used=False)
    local_name = "rebound" if "rebound" in recognized_import else "build_calculation_lineage"
    (tmp_path / "src" / "owner" / "consumer.py").write_text(
        "from decimal import Decimal\n"
        "from owner.numeric_policy import TEST_LEDGER_OUTPUT_V1\n"
        f"{local_name} = unrelated_builder\n"
        f"{recognized_import}\n"
        "TEST_LEDGER_OUTPUT_V1.normalize(Decimal('1'), field_name='value')\n"
        f"{builder_call}("
        "numeric_output_policy=TEST_LEDGER_OUTPUT_V1.lineage_identity())\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path, _contract(tmp_path)) == ()


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
            "policy keys must include",
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


# Fixed reviewed source fixtures: independent of live producer/guard files.
_TYPED_RETAINED_OWNER_FIXTURE = 'from collections.abc import Mapping\nfrom dataclasses import dataclass, replace\nfrom decimal import Decimal, InvalidOperation\nfrom typing import Literal, cast\nfrom portfolio_common.domain.calculation_lineage import build_calculation_lineage, calculation_lineage_binds_output, calculation_lineage_from_payload, canonical_content_hash\nfrom .fx_source_admission import FX_SOURCE_ADMISSION_TYPES\nfrom .fx_source_presence import fx_original_pnl_values, fx_source_presence_input_payload\nfrom .numeric_policy import TRANSACTION_COST_LEDGER_OUTPUT_V1\nfrom .payload_identity import transaction_payload_fingerprint, transaction_payload_pre_upstream_fingerprint\nFxCurrencyBasis = Literal[\'local\', \'base\']\n\nclass SourceEvidenceConfirmationRejected(ValueError):\n    """Bounded reason without input values or financial identifiers."""\n\n@dataclass(frozen=True, slots=True)\nclass FxPnlBasisEvidence:\n    source: Decimal | None\n    capital: Decimal\n    fx: Decimal\n    total: Decimal\n\n    def __post_init__(self) -> None:\n        for field_name in (\'source\', \'capital\', \'fx\', \'total\'):\n            value = getattr(self, field_name)\n            if value is None and field_name == \'source\':\n                continue\n            if not isinstance(value, Decimal):\n                raise TypeError(\'FX evidence values must be Decimal\')\n            if not value.is_finite():\n                raise ValueError(\'FX evidence values must be finite\')\n\n@dataclass(frozen=True, slots=True)\nclass FxSourceEvidenceConfirmation:\n    local: FxPnlBasisEvidence\n    base: FxPnlBasisEvidence\n    confirmed_bases: tuple[FxCurrencyBasis, ...] = ()\n\n    def __post_init__(self) -> None:\n        if not isinstance(self.local, FxPnlBasisEvidence) or not isinstance(self.base, FxPnlBasisEvidence):\n            raise TypeError(\'FX confirmation requires typed currency-basis evidence\')\n\ndef retained_fx_output_payload(ledger_output: Mapping[str, object]) -> dict[str, object]:\n    """Complete persisted FX output projection; never manufacture an old receipt."""\n    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1\n    quantum = Decimal(1).scaleb(-policy.scale)\n    output: dict[str, object] = {}\n    for name, value in ledger_output.items():\n        if value is None:\n            continue\n        if isinstance(value, Decimal):\n            with policy.arithmetic_context():\n                value = policy.normalize(value, field_name=name).quantize(quantum, rounding=policy.rounding)\n        output[name] = value\n    return output\n\ndef _verify_v1_fx_source(*, raw_source: Mapping[str, object], ledger_output: Mapping[str, object], receipt_payload: object) -> FxSourceEvidenceConfirmation:\n    receipt = calculation_lineage_from_payload(receipt_payload)\n    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1\n    if receipt is None or receipt.algorithm_id != \'foreign-exchange-baseline-processing\' or receipt.algorithm_version != 1 or (receipt.intermediate_precision != policy.working_precision) or (receipt.numeric_output_policy != policy.lineage_identity()) or (not calculation_lineage_binds_output(receipt, output_payload=retained_fx_output_payload(ledger_output))):\n        raise SourceEvidenceConfirmationRejected(\'FX_SOURCE_RECEIPT_UNAVAILABLE\')\n    return FxSourceEvidenceConfirmation(local=_retained_basis(raw_source, ledger_output, \'local\'), base=_retained_basis(raw_source, ledger_output, \'base\'))\n\ndef _verify_v2_fx_source(*, raw_source: Mapping[str, object], ledger_output: Mapping[str, object], receipt_payload: object) -> FxSourceEvidenceConfirmation:\n    receipt = calculation_lineage_from_payload(receipt_payload)\n    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1\n    if receipt is None or receipt.algorithm_id != \'foreign-exchange-baseline-processing\' or receipt.algorithm_version != 2 or (receipt.intermediate_precision != policy.working_precision) or (receipt.numeric_output_policy != policy.lineage_identity()) or (not calculation_lineage_binds_output(receipt, output_payload=retained_fx_output_payload(ledger_output))):\n        raise SourceEvidenceConfirmationRejected(\'FX_SOURCE_RECEIPT_UNAVAILABLE\')\n    if receipt.input_content_hash != canonical_content_hash(fx_source_presence_input_payload(source_values=fx_original_pnl_values(raw_source), booked_output=retained_fx_output_payload(ledger_output))):\n        raise SourceEvidenceConfirmationRejected(\'FX_SOURCE_INPUT_UNAVAILABLE\')\n    return FxSourceEvidenceConfirmation(local=_retained_basis(raw_source, ledger_output, \'local\'), base=_retained_basis(raw_source, ledger_output, \'base\'))\n\ndef _retained_basis(raw: Mapping[str, object], output: Mapping[str, object], basis: str) -> FxPnlBasisEvidence:\n    source = raw.get(f\'realized_fx_pnl_{basis}\')\n    if source is not None:\n        if not isinstance(source, (str, Decimal)):\n            raise SourceEvidenceConfirmationRejected(\'FX_SOURCE_AMOUNT_INVALID\')\n        try:\n            source = TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(Decimal(source), field_name=\'fx_source\')\n        except (InvalidOperation, ValueError, ArithmeticError):\n            raise SourceEvidenceConfirmationRejected(\'FX_SOURCE_AMOUNT_INVALID\') from None\n        if source != output.get(f\'realized_fx_pnl_{basis}\'):\n            raise SourceEvidenceConfirmationRejected(\'FX_SOURCE_OUTPUT_MISMATCH\')\n    try:\n        return FxPnlBasisEvidence(source=cast(Decimal | None, source), capital=cast(Decimal, output[f\'realized_capital_pnl_{basis}\']), fx=cast(Decimal, output[f\'realized_fx_pnl_{basis}\']), total=cast(Decimal, output[f\'realized_total_pnl_{basis}\']))\n    except (KeyError, TypeError, ValueError):\n        raise SourceEvidenceConfirmationRejected(\'FX_SOURCE_OUTPUT_UNAVAILABLE\') from None'
_TYPED_PRESENCE_FIXTURE = '"""Bind original FX P/L presence separately from normalized booked economics."""\n\nfrom collections.abc import Mapping\nfrom decimal import Decimal, InvalidOperation\n\nFX_ORIGINAL_PNL_PRESENCE_POLICY = "fx-original-pnl-presence@2"\nFX_ORIGINAL_PNL_FIELDS = (\n    "realized_capital_pnl_local",\n    "realized_fx_pnl_local",\n    "realized_total_pnl_local",\n    "realized_capital_pnl_base",\n    "realized_fx_pnl_base",\n    "realized_total_pnl_base",\n)\n\n\ndef fx_original_pnl_values(raw_source: Mapping[str, object]) -> dict[str, object]:\n    """Recover six exact retained source values, never persisted defaulted amounts."""\n    values: dict[str, object] = {}\n    for name in FX_ORIGINAL_PNL_FIELDS:\n        value = raw_source.get(name)\n        if value is not None:\n            if not isinstance(value, (str, Decimal)):\n                raise ValueError("Original FX source amount is not exact decimal text")\n            try:\n                value = Decimal(value)\n            except InvalidOperation:\n                raise ValueError("Original FX source amount is invalid") from None\n            if not value.is_finite():\n                raise ValueError("Original FX source amount must be finite")\n        values[name] = value\n    return values\n\n\ndef fx_source_presence_input_payload(\n    *, source_values: Mapping[str, object], booked_output: Mapping[str, object]\n) -> dict[str, object]:\n    """Produce the v2 input projection independently of service calculation code.\n\n    A null original amount is not an explicit zero. Original finite Decimal values\n    remain unrounded; booked economics have their existing governed output scale.\n    The complete booked projection binds all unchanged inputs and derived outputs.\n    This receipt does not itself confirm an absent source or revise financial values.\n    """\n    original: dict[str, object] = {}\n    for name in FX_ORIGINAL_PNL_FIELDS:\n        if name not in source_values:\n            raise ValueError(f"Original FX source projection is missing {name}")\n        value = source_values[name]\n        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):\n            raise ValueError(f"Original FX source {name} must be a finite Decimal or null")\n        original[name] = {"present": value is not None, "value": value}\n    return {\n        "source_presence_policy": FX_ORIGINAL_PNL_PRESENCE_POLICY,\n        "original_pnl": original,\n        "booked_economics": dict(booked_output),\n    }\n'

def _typed_original_presence_fixture(root: Path, version: int = 2) -> tuple[Path, Path, Path]:
    """Exercise the actual structural grammar, independent of shipping callable names."""
    _write_policy(root)
    module = ast.parse(_TYPED_RETAINED_OWNER_FIXTURE)
    retained = root / "src/owner/retained.py"
    chosen = {"retained_fx_output_payload", "_retained_basis", f"_verify_v{version}_fx_source"}
    classes = {
        "SourceEvidenceConfirmationRejected",
        "FxPnlBasisEvidence",
        "FxSourceEvidenceConfirmation",
    }
    nodes = [
        node
        for node in module.body
        if (
            isinstance(node, ast.ImportFrom)
            or isinstance(node, ast.FunctionDef)
            and node.name in chosen
            or isinstance(node, ast.ClassDef)
            and node.name in classes
            or isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "FxCurrencyBasis"
                for target in node.targets
            )
        )
    ]

    class FixtureImports(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == "numeric_policy":
                node.module, node.level = "owner.numeric_policy", 0
                node.names = [ast.alias(name="TEST_LEDGER_OUTPUT_V1")]
            elif node.module == "fx_source_presence":
                node.module, node.level = "owner.presence", 0
            return node

        def visit_Name(self, node):
            if node.id == "TRANSACTION_COST_LEDGER_OUTPUT_V1":
                node.id = "TEST_LEDGER_OUTPUT_V1"
            return node

    authored = FixtureImports().visit(ast.Module(body=nodes, type_ignores=[]))
    retained.write_text(ast.unparse(authored) + "\n", encoding="utf-8")
    presence = root / "src/owner/presence.py"
    presence.write_text(
        _TYPED_PRESENCE_FIXTURE, encoding="utf-8"
    )
    boundary = f"src/owner/retained.py::_verify_v{version}_fx_source"
    spec = {
        "receipt_parameter": "receipt_payload",
        "output_parameter": "ledger_output",
        "output_canonicalizer": "src/owner/retained.py::retained_fx_output_payload",
        "algorithm_id": "foreign-exchange-baseline-processing",
        "algorithm_version": version,
    }
    if version == 2:
        spec["input_verification"] = {
            "source_parameter": "raw_source",
            "source_projector": "src/owner/presence.py::fx_original_pnl_values",
            "input_builder": "src/owner/presence.py::fx_source_presence_input_payload",
            "presence_policy": "fx-original-pnl-presence@2",
        }
    contract = _contract(
        root,
        lineage_boundary_callsites=[boundary],
        lineage_boundary_covered_callsites={
            boundary: [
                "src/owner/retained.py::_retained_basis",
                "src/owner/retained.py::retained_fx_output_payload",
            ]
        },
        lineage_verification_boundaries={boundary: spec},
    )
    return retained, presence, contract


@pytest.mark.parametrize("version", [1, 2])
def test_typed_finite_original_source_basis_boundary_is_proved(tmp_path, version):
    _, _, contract = _typed_original_presence_fixture(tmp_path, version)
    assert evaluate(tmp_path, contract) == ()


def test_original_presence_proof_accepts_alpha_renamed_classes_helpers_and_locals(tmp_path):
    retained, presence, contract = _typed_original_presence_fixture(tmp_path)
    renames = {
        "FxPnlBasisEvidence": "FiniteBasis",
        "FxSourceEvidenceConfirmation": "FinitePair",
        "_retained_basis": "project_basis",
        "fx_original_pnl_values": "extract_presence",
        "fx_source_presence_input_payload": "bind_presence",
        "FX_ORIGINAL_PNL_FIELDS": "ORIGINAL_FIELDS",
    }
    for path in (retained, presence, contract):
        source = path.read_text(encoding="utf-8")
        for before, after in renames.items():
            source = source.replace(before, after)
        if path != contract:

            class RenameLocal(ast.NodeTransformer):
                def visit_Name(self, node):
                    if node.id == "field_name":
                        node.id = "column_name"
                    return node

            source = ast.unparse(RenameLocal().visit(ast.parse(source)))
        path.write_text(source, encoding="utf-8")
    assert evaluate(tmp_path, contract) == ()


@pytest.mark.parametrize(
    "before,after",
    [
        ("receipt.input_content_hash !=", "receipt.output_content_hash !="),
        ("receipt.input_content_hash !=", "receipt.input_content_hash =="),
        ("fx_original_pnl_values(raw_source)", "fx_original_pnl_values({})"),
        ("booked_output=retained_fx_output_payload(ledger_output)", "booked_output={}"),
        ("receipt.algorithm_version != 2", "receipt.algorithm_version != 1"),
        (
            "receipt.algorithm_id != 'foreign-exchange-baseline-processing'",
            "receipt.algorithm_id != 'foreign-algorithm'",
        ),
        (
            "receipt.intermediate_precision != policy.working_precision",
            "receipt.intermediate_precision != 18",
        ),
        ("receipt.numeric_output_policy != policy.lineage_identity()", "False"),
        (
            "not calculation_lineage_binds_output(receipt, "
            "output_payload=retained_fx_output_payload(ledger_output))",
            "False",
        ),
        ("@dataclass(frozen=True, slots=True)", "@dataclass(frozen=False, slots=True)"),
        ("if not value.is_finite():", "if False:"),
        (
            "capital=cast(Decimal, output[f'realized_capital_pnl_{basis}'])",
            "capital=cast(Decimal, output[f'realized_fx_pnl_{basis}'])",
        ),
        (
            "local=_retained_basis(raw_source, ledger_output, 'local')",
            "local=_retained_basis(raw_source, ledger_output, 'base')",
        ),
        ("output[name] = value", "output['constant'] = value"),
    ],
)
def test_v2_typed_receipt_rejects_bound_input_output_and_basis_drift(tmp_path, before, after):
    retained, _, contract = _typed_original_presence_fixture(tmp_path)
    original = retained.read_text(encoding="utf-8")
    assert before in original
    retained.write_text(original.replace(before, after), encoding="utf-8")
    assert evaluate(tmp_path, contract)


@pytest.mark.parametrize(
    "before,after",
    [
        ('"realized_total_pnl_base",', ""),
        ('"present": value is not None', '"present": True'),
        ('"value": value', '"value": Decimal("0")'),
        ("dict(booked_output)", "{}"),
        ("raw_source.get(name)", 'raw_source.get(name) or "0"'),
        ("if value is not None:", "if False:"),
        ("not value.is_finite()", "False"),
        ("fx-original-pnl-presence@2", "foreign-presence-policy"),
    ],
)
def test_v2_presence_projection_rejects_omission_defaults_and_unbound_output(
    tmp_path, before, after
):
    _, presence, contract = _typed_original_presence_fixture(tmp_path)
    original = presence.read_text(encoding="utf-8")
    assert before in original
    presence.write_text(original.replace(before, after), encoding="utf-8")
    assert evaluate(tmp_path, contract)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_descriptor",
        "missing_rejection",
        "mutable_return",
        "shadow_hash",
        "shadow_builtin",
        "source_alias",
        "opaque_helper",
    ],
)
def test_v2_registration_cannot_allow_bypass_shadowing_or_opaque_results(tmp_path, mutation):
    retained, presence, contract = _typed_original_presence_fixture(tmp_path)
    text = retained.read_text(encoding="utf-8")
    if mutation == "missing_descriptor":
        payload = json.loads(contract.read_text(encoding="utf-8"))
        spec = next(
            iter(
                payload["policies"]["TEST_LEDGER_OUTPUT_V1"][
                    "lineage_verification_boundaries"
                ].values()
            )
        )
        del spec["input_verification"]
        contract.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "missing_rejection":
        text = text.replace(
            "if receipt.input_content_hash !=", "if False and receipt.input_content_hash !="
        )
    elif mutation == "mutable_return":
        start = text.index("    return FxSourceEvidenceConfirmation(")
        end = text.index("\ndef _retained_basis", start)
        text = text[:start] + "    return [ledger_output]\n" + text[end:]
    elif mutation == "shadow_hash":
        text += "\ncanonical_content_hash = lambda value: '0' * 64\n"
    elif mutation == "shadow_builtin":
        presence.write_text(
            presence.read_text(encoding="utf-8") + "\ndict = lambda value: {}\n", encoding="utf-8"
        )
    elif mutation == "source_alias":
        text = text.replace(
            "    receipt = calculation_lineage_from_payload(receipt_payload)",
            "    raw_source = {}\n    receipt = calculation_lineage_from_payload(receipt_payload)",
        )
    else:
        text = text.replace(
            "source = raw.get(f'realized_fx_pnl_{basis}')", "source = mutate(output)"
        )
        text += "\ndef mutate(output):\n    output.clear()\n    return None\n"
    retained.write_text(text, encoding="utf-8")
    assert evaluate(tmp_path, contract)


def _execute_typed_presence_fixture(retained: Path, presence: Path):
    from collections.abc import Mapping
    from dataclasses import dataclass
    from decimal import InvalidOperation
    from typing import Literal, cast

    from portfolio_common.domain.calculation_lineage import (
        build_calculation_lineage,
        calculation_lineage_binds_output,
        calculation_lineage_from_payload,
        canonical_content_hash,
    )
    from portfolio_common.domain.transaction.numeric_policy import TRANSACTION_COST_LEDGER_OUTPUT_V1

    namespace = dict(
        __name__="typed_source_guard_fixture",
        Mapping=Mapping,
        dataclass=dataclass,
        Decimal=Decimal,
        InvalidOperation=InvalidOperation,
        Literal=Literal,
        cast=cast,
        TEST_LEDGER_OUTPUT_V1=TRANSACTION_COST_LEDGER_OUTPUT_V1,
        calculation_lineage_binds_output=calculation_lineage_binds_output,
        calculation_lineage_from_payload=calculation_lineage_from_payload,
        canonical_content_hash=canonical_content_hash,
    )
    for path in (presence, retained):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        tree.body = [
            node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        exec(compile(tree, "<typed-source-proof-fixture>", "exec", dont_inherit=True), namespace)
    raw = {
        f"realized_{component}_pnl_{basis}": "0"
        for basis in ("local", "base")
        for component in ("capital", "fx", "total")
    }
    output = {name: Decimal(value) for name, value in raw.items()}
    payload = namespace["fx_source_presence_input_payload"](
        source_values=namespace["fx_original_pnl_values"](raw),
        booked_output=namespace["retained_fx_output_payload"](output),
    )
    receipt = build_calculation_lineage(
        algorithm_id="foreign-exchange-baseline-processing",
        algorithm_version=2,
        intermediate_precision=64,
        input_payload=payload,
        output_payload=namespace["retained_fx_output_payload"](output),
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
    ).lineage_payload()
    return namespace["_verify_v2_fx_source"], raw, output, receipt


def test_v2_actual_receipt_rejects_changed_presence_before_deriving_amounts(tmp_path):
    retained, presence, contract = _typed_original_presence_fixture(tmp_path)
    verify, raw, output, receipt = _execute_typed_presence_fixture(retained, presence)
    assert verify(raw_source=raw, ledger_output=output, receipt_payload=receipt).local.source == 0
    raw["realized_fx_pnl_local"] = None
    with pytest.raises(ValueError, match="INPUT_UNAVAILABLE"):
        verify(raw_source=raw, ledger_output=output, receipt_payload=receipt)
    assert evaluate(tmp_path, contract) == ()


def test_v2_guard_rejects_executed_post_receipt_mutation_in_typed_helper(tmp_path):
    retained, presence, contract = _typed_original_presence_fixture(tmp_path)
    original = retained.read_text(encoding="utf-8")
    mutated = original.replace(
        "source = raw.get(f'realized_fx_pnl_{basis}')",
        "output[f'realized_fx_pnl_{basis}'] = Decimal('99')\n"
        "    output[f'realized_total_pnl_{basis}'] = Decimal('99')\n"
        "    source = Decimal('99')",
    )
    assert mutated != original
    retained.write_text(mutated, encoding="utf-8")
    verify, raw, output, receipt = _execute_typed_presence_fixture(retained, presence)
    assert verify(raw_source=raw, ledger_output=output, receipt_payload=receipt).local.source == 99
    assert output["realized_fx_pnl_local"] == 99
    assert evaluate(tmp_path, contract)


@pytest.mark.parametrize("version", ["2", None, True, 0, [], {}])
def test_typed_verification_malformed_version_is_a_finding_not_a_crash(tmp_path, version):
    _, _, contract = _typed_original_presence_fixture(tmp_path)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    specifications = payload["policies"]["TEST_LEDGER_OUTPUT_V1"]["lineage_verification_boundaries"]
    next(iter(specifications.values()))["algorithm_version"] = version
    contract.write_text(json.dumps(payload), encoding="utf-8")
    assert evaluate(tmp_path, contract)


@pytest.mark.parametrize(
    "extra", ["MUTATION = dict.clear({})", "Decimal = str", "from decimal import Decimal as dict"]
)
def test_v2_source_module_refuses_effectful_assignments_or_shadowed_bindings(tmp_path, extra):
    _, presence, contract = _typed_original_presence_fixture(tmp_path)
    presence.write_text(
        presence.read_text(encoding="utf-8") + "\n" + extra + "\n", encoding="utf-8"
    )
    assert evaluate(tmp_path, contract)


@pytest.mark.parametrize("shape", ["empty", "missing_loop", "non_loop", "unnamed_target"])
def test_v2_projection_malformed_shape_is_refused_without_crashing(tmp_path, shape):
    _, presence, contract = _typed_original_presence_fixture(tmp_path)
    module = ast.parse(presence.read_text(encoding="utf-8"))
    projector = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "fx_original_pnl_values"
    )
    if shape == "empty":
        projector.body = [ast.Pass()]
    elif shape == "missing_loop":
        projector.body = projector.body[:1]
    else:
        loop = next(node for node in projector.body if isinstance(node, ast.For))
        if shape == "non_loop":
            projector.body[projector.body.index(loop)] = ast.Pass()
        else:
            loop.target = ast.Tuple(elts=[ast.Name(id="field", ctx=ast.Store())], ctx=ast.Store())
    presence.write_text(ast.unparse(ast.fix_missing_locations(module)), encoding="utf-8")
    assert evaluate(tmp_path, contract)

@pytest.mark.parametrize(
    "suffix",
    [
        "def harmless(raw: Mapping[str, object], limit: int = 1, *, absent: object = None) -> dict[str, object]:\n    return {}\n",
        "def harmless(raw: 'Mapping[str, object]') -> 'dict[str, object]':\n    return {}\n",
    ],
)
def test_v2_presence_owner_keeps_supported_inert_headers(tmp_path, suffix):
    _, presence, contract = _typed_original_presence_fixture(tmp_path)
    presence.write_text(presence.read_text(encoding="utf-8") + "\n" + suffix, encoding="utf-8")
    assert evaluate(tmp_path, contract) == ()


@pytest.mark.parametrize(
    "header",
    [
        "def unrelated(default=EFFECT):\n    pass\n",
        "def unrelated(*, default=EFFECT):\n    pass\n",
        "def unrelated(value: EFFECT):\n    pass\n",
        "def unrelated() -> EFFECT:\n    pass\n",
        "@(EFFECT or (lambda fn: fn))\ndef unrelated():\n    pass\n",
    ],
)
def test_v2_presence_owner_refuses_import_time_rebinding(tmp_path, header):
    _, presence, contract = _typed_original_presence_fixture(tmp_path)
    effect = (
        "globals().__setitem__('fx_original_pnl_values', "
        "lambda raw: {name: None for name in FX_ORIGINAL_PNL_FIELDS})"
    )
    source = presence.read_text(encoding="utf-8") + "\n" + header.replace("EFFECT", effect)
    presence.write_text(source, encoding="utf-8")
    namespace = {}
    exec(
        compile(source, "<external-import-effect-control>", "exec", dont_inherit=True),
        namespace,
    )
    assert namespace["fx_original_pnl_values"]({"realized_fx_pnl_local": "0"})[
        "realized_fx_pnl_local"
    ] is None
    assert evaluate(tmp_path, contract)


@pytest.mark.parametrize(
    "change",
    [
        "selected-argument-annotation",
        "selected-return-annotation",
        "selected-default",
        "selected-decorator",
        "unapproved-import",
        "shadowed-annotation-type",
        "module-class",
    ],
)
def test_v2_presence_owner_refuses_unsupported_definition_grammar(tmp_path, change):
    _, presence, contract = _typed_original_presence_fixture(tmp_path)
    source = presence.read_text(encoding="utf-8")
    effect = "globals().__setitem__('fx_original_pnl_values', lambda raw: {})"
    if change == "selected-argument-annotation":
        source = source.replace("raw_source: Mapping[str, object]", "raw_source: " + effect)
    elif change == "selected-return-annotation":
        source = source.replace(") -> dict[str, object]:", ") -> " + effect + ":", 1)
    elif change == "selected-default":
        source = source.replace("raw_source: Mapping[str, object]", "raw_source: Mapping[str, object] = " + effect)
    elif change == "selected-decorator":
        source = source.replace("def fx_original_pnl_values", "@(lambda fn: fn)\ndef fx_original_pnl_values")
    elif change == "unapproved-import":
        source += "\nfrom unapproved_owner import register\n"
    elif change == "shadowed-annotation-type":
        source += "\nstr = 'not-a-type'\ndef unrelated(value: str):\n    pass\n"
    else:
        source += "\nclass Unadmitted:\n    pass\n"
    presence.write_text(source, encoding="utf-8")
    assert evaluate(tmp_path, contract)
