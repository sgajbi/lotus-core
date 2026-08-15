"""Mutation tests for the bond quote authority guard."""

from pathlib import Path

from scripts.quality.bond_quote_authority_guard import REQUIRED_CONSUMERS, evaluate


def _write_required_consumers(root: Path) -> None:
    for relative, required_consumer in REQUIRED_CONSUMERS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        arguments = ", ".join(
            f"{name}={expression}"
            for name, expression in required_consumer.keyword_expressions.items()
        )
        path.write_text(
            f"def {required_consumer.function_name}():\n"
            f"    if requires_bond_quote_authority({arguments}):\n"
            "        raise ValueError('missing authority')\n",
            encoding="utf-8",
        )


def test_repository_has_no_production_bond_quote_heuristic() -> None:
    root = Path(__file__).resolve().parents[3]

    assert evaluate(root) == ()


def test_guard_rejects_deleted_heuristic_identifier(tmp_path: Path) -> None:
    _write_required_consumers(tmp_path)
    source = tmp_path / "src" / "pricing.py"
    source.write_text("resolve_valuation_unit_price(price)\n", encoding="utf-8")

    assert evaluate(tmp_path) == (
        "src/pricing.py: forbidden bond quote heuristic: resolve_valuation_unit_price",
    )


def test_guard_requires_each_production_consumer_to_fail_closed(tmp_path: Path) -> None:
    _write_required_consumers(tmp_path)
    target = tmp_path / next(iter(REQUIRED_CONSUMERS))
    target.write_text("value = quantity * price\n", encoding="utf-8")

    assert evaluate(tmp_path) == (
        f"{target.relative_to(tmp_path).as_posix()}: "
        "required function "
        f"{REQUIRED_CONSUMERS[next(iter(REQUIRED_CONSUMERS))].function_name} "
        "is missing or ambiguous",
    )


def test_guard_does_not_accept_authority_identifier_in_a_comment(tmp_path: Path) -> None:
    _write_required_consumers(tmp_path)
    target = tmp_path / next(iter(REQUIRED_CONSUMERS))
    target.write_text("# requires_bond_quote_authority\nvalue = quantity * price\n")

    assert evaluate(tmp_path) == (
        f"{target.relative_to(tmp_path).as_posix()}: "
        "required function "
        f"{REQUIRED_CONSUMERS[next(iter(REQUIRED_CONSUMERS))].function_name} "
        "is missing or ambiguous",
    )


def test_guard_requires_complete_authority_inputs(tmp_path: Path) -> None:
    _write_required_consumers(tmp_path)
    target = tmp_path / next(iter(REQUIRED_CONSUMERS))
    required_consumer = REQUIRED_CONSUMERS[next(iter(REQUIRED_CONSUMERS))]
    target.write_text(
        f"def {required_consumer.function_name}():\n"
        "    if requires_bond_quote_authority(product_type=kind):\n"
        "        raise ValueError('missing authority')\n"
    )

    assert evaluate(tmp_path) == (
        f"{target.relative_to(tmp_path).as_posix()}: {required_consumer.function_name} "
        "bond quote-authority branch must use the governed product, quantity, and cost evidence",
    )


def test_guard_rejects_unused_authority_call(tmp_path: Path) -> None:
    _write_required_consumers(tmp_path)
    relative = next(iter(REQUIRED_CONSUMERS))
    required_consumer = REQUIRED_CONSUMERS[relative]
    target = tmp_path / relative
    arguments = ", ".join(
        f"{name}={expression}" for name, expression in required_consumer.keyword_expressions.items()
    )
    target.write_text(
        f"def {required_consumer.function_name}():\n"
        f"    requires_bond_quote_authority({arguments})\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path) == (
        f"{relative.as_posix()}: {required_consumer.function_name} must have exactly one "
        "direct bond quote-authority fail-closed branch",
    )


def test_guard_rejects_authority_call_in_wrong_function(tmp_path: Path) -> None:
    _write_required_consumers(tmp_path)
    relative = next(iter(REQUIRED_CONSUMERS))
    required_consumer = REQUIRED_CONSUMERS[relative]
    target = tmp_path / relative
    target.write_text(
        "def dummy():\n"
        "    if requires_bond_quote_authority(product_type=None, quantity=0, "
        "cost_basis_reporting=0, cost_basis_local=0):\n"
        "        raise ValueError('missing authority')\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path) == (
        f"{relative.as_posix()}: required function {required_consumer.function_name} "
        "is missing or ambiguous",
    )


def test_guard_rejects_constant_authority_inputs(tmp_path: Path) -> None:
    _write_required_consumers(tmp_path)
    relative = next(iter(REQUIRED_CONSUMERS))
    required_consumer = REQUIRED_CONSUMERS[relative]
    target = tmp_path / relative
    target.write_text(
        f"def {required_consumer.function_name}():\n"
        "    if requires_bond_quote_authority(product_type=None, quantity=0, "
        "cost_basis_reporting=0, cost_basis_local=0):\n"
        "        raise ValueError('missing authority')\n",
        encoding="utf-8",
    )

    assert evaluate(tmp_path) == (
        f"{relative.as_posix()}: {required_consumer.function_name} bond quote-authority "
        "branch must use the governed product, quantity, and cost evidence",
    )
