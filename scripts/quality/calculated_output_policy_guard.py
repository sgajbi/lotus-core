"""Validate the complete calculated financial-output policy inventory."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = Path("docs/standards/financial-calculated-output-policies.v1.json")
POLICY_KEYS = {
    "declaration_path",
    "owner",
    "output_family",
    "name",
    "version",
    "precision",
    "scale",
    "working_precision",
    "rounding",
    "lineage_binding",
    "lineage_gap_callsites",
}
OPTIONAL_POLICY_KEYS = {
    "lineage_boundary_callsites",
    "lineage_boundary_covered_callsites",
    "lineage_boundary_terminal_callsites",
    "lineage_verification_boundaries",
}
LINEAGE_BINDINGS = {"required", "partial", "not-exposed"}
EXECUTION_METHODS = {
    "add",
    "arithmetic_context",
    "divide",
    "multiply",
    "normalize",
    "subtract",
}
CALCULATION_LINEAGE_MODULE = "portfolio_common.domain.calculation_lineage"
CALCULATION_LINEAGE_BUILDER = "build_calculation_lineage"


class _RetainedVerificationProof:
    """Fail-closed proof for straight-line retained-receipt rejection boundaries.

    Only import-resolved strict decoding, expected policy/algorithm checks and a
    negative output-binding predicate that raises can authorize a normal return.
    Other control-flow shapes are deliberately unsupported, not guessed safe.
    """

    def __init__(
        self,
        path: str,
        constant: str,
        declaration: PolicyDeclaration,
        specification: dict[str, Any],
        covered: set[str],
    ) -> None:
        self.path, self.constant, self.specification = path, constant, specification
        self.policy = f"{_source_module(declaration.declaration_path)}.{constant}"
        self.covered = covered
        self.aliases: dict[str, str | None] = {}
        self.facts: set[str] = set()
        self.covered_parameters: dict[str, tuple[list[str], str]] = {}

    def symbol(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id)
        if isinstance(node, ast.Attribute):
            root = self.symbol(node.value)
            return f"{root}.{node.attr}" if root is not None else None
        if not isinstance(node, ast.Call):
            return None
        function = self.symbol(node.func)
        if (
            function == f"{CALCULATION_LINEAGE_MODULE}.calculation_lineage_from_payload"
            and len(node.args) == 1
            and not node.keywords
            and self.symbol(node.args[0]) == "@receipt_input"
        ):
            return "@decoded"
        if (
            function == self.specification["output_canonicalizer"]
            and len(node.args) == 1
            and not node.keywords
            and self.symbol(node.args[0]) == "@output"
        ):
            return "@canonical_output"
        if function == f"{self.policy}.lineage_identity" and not node.args and not node.keywords:
            return "@expected_policy"
        return None

    def rejection_facts(self, node: ast.expr) -> set[str]:
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            return set().union(*(self.rejection_facts(value) for value in node.values))
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
            left, right, operator = self.symbol(node.left), node.comparators[0], node.ops[0]
            if (
                left == "@decoded"
                and isinstance(operator, ast.Is)
                and isinstance(right, ast.Constant)
                and right.value is None
            ):
                return {"present"}
            if not isinstance(operator, ast.NotEq):
                return set()
            expected = {
                "@decoded.algorithm_id": self.specification["algorithm_id"],
                "@decoded.algorithm_version": self.specification["algorithm_version"],
            }
            if (
                left in expected
                and isinstance(right, ast.Constant)
                and type(right.value) is type(expected[left])
                and right.value == expected[left]
            ):
                return {cast(str, left)}
            if (
                left == "@decoded.intermediate_precision"
                and self.symbol(right) == f"{self.policy}.working_precision"
            ):
                return {"precision"}
            if (
                left == "@decoded.numeric_output_policy"
                and self.symbol(right) == "@expected_policy"
            ):
                return {"policy"}
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.Not)
            and isinstance(node.operand, ast.Call)
        ):
            call = node.operand
            if (
                self.symbol(call.func)
                == f"{CALCULATION_LINEAGE_MODULE}.calculation_lineage_binds_output"
                and len(call.args) == 1
                and self.symbol(call.args[0]) == "@decoded"
                and len(call.keywords) == 1
                and call.keywords[0].arg == "output_payload"
                and self.symbol(call.keywords[0].value) == "@canonical_output"
            ):
                return {"bound_output"}
        return set()

    def complete(self) -> bool:
        return self.facts == {
            "present",
            "@decoded.algorithm_id",
            "@decoded.algorithm_version",
            "precision",
            "policy",
            "bound_output",
        }

    def canonicalizer_projects_input(
        self, function: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str
    ) -> bool:
        """Recognize pure field projections, never merely an argument-taking helper.

        Supported forms are a literal field map normalized from the identical input
        keys, or a full items() copy that omits only None and applies the governed
        Decimal normalization/quantization. Other shapes require separate proof.
        """
        saved_aliases = self.aliases.copy()
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ):
            self.aliases[argument.arg] = None
        self.aliases[parameter] = "@output"
        body = [
            statement
            for statement in function.body
            if not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
        ]
        try:
            if len(body) == 1 and isinstance(body[0], ast.Return):
                projection = body[0].value
                if not isinstance(projection, ast.Dict) or not projection.keys:
                    return False
                keys: set[str] = set()
                for key, value in zip(projection.keys, projection.values):
                    if (
                        not isinstance(key, ast.Constant)
                        or not isinstance(key.value, str)
                        or not key.value
                        or key.value in keys
                        or not isinstance(value, ast.Call)
                        or self.symbol(value.func) != f"{self.policy}.normalize"
                        or len(value.args) != 1
                        or len(value.keywords) != 1
                        or value.keywords[0].arg != "field_name"
                        or ast.dump(value.keywords[0].value) != ast.dump(key)
                    ):
                        return False
                    source = value.args[0]
                    if (
                        not isinstance(source, ast.Subscript)
                        or self.symbol(source.value) != "@output"
                        or ast.dump(source.slice) != ast.dump(key)
                    ):
                        return False
                    keys.add(key.value)
                return True
            return self.complete_mapping_projection(body, parameter)
        finally:
            self.aliases = saved_aliases

    def complete_mapping_projection(self, body: list[ast.stmt], parameter: str) -> bool:
        """Fail closed outside the immutable policy-scaled complete-mapping grammar."""
        if len(body) != 5:
            return False
        policy_assignment, quantum_assignment, output_assignment, loop, result = body
        if (
            not isinstance(policy_assignment, ast.Assign)
            or len(policy_assignment.targets) != 1
            or not isinstance(policy_assignment.targets[0], ast.Name)
            or self.symbol(policy_assignment.value) != self.policy
            or not isinstance(quantum_assignment, ast.Assign)
            or len(quantum_assignment.targets) != 1
            or not isinstance(quantum_assignment.targets[0], ast.Name)
            or not isinstance(loop, ast.For)
            or not isinstance(loop.target, ast.Tuple)
            or len(loop.target.elts) != 2
            or not all(isinstance(item, ast.Name) for item in loop.target.elts)
        ):
            return False
        if isinstance(output_assignment, ast.AnnAssign) and output_assignment.value is not None:
            output_assignment = ast.Assign(
                targets=[output_assignment.target], value=output_assignment.value
            )
        if (
            not isinstance(output_assignment, ast.Assign)
            or len(output_assignment.targets) != 1
            or not isinstance(output_assignment.targets[0], ast.Name)
        ):
            return False
        policy_name = policy_assignment.targets[0].id
        quantum_name = quantum_assignment.targets[0].id
        output_name = output_assignment.targets[0].id
        key_name, value_name = [cast(ast.Name, item).id for item in loop.target.elts]
        if len({parameter, policy_name, quantum_name, output_name, key_name, value_name}) != 6:
            return False
        decimal_types = [
            node.args[1]
            for node in ast.walk(loop)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) == 2
        ]
        if (
            "isinstance" in self.aliases
            or len(decimal_types) != 1
            or self.symbol(decimal_types[0]) != "decimal.Decimal"
        ):
            return False
        local_names = {policy_name, quantum_name, output_name, key_name, value_name}
        decimal_root = ast.unparse(decimal_types[0]).split(".")[0]
        if local_names & {"isinstance", decimal_root}:
            return False
        # Alpha-renamed AST grammar: identifiers/import aliases are not a source hash.
        decimal_type = ast.unparse(decimal_types[0])
        policy_source = ast.unparse(policy_assignment.value)
        expected = ast.parse(
            f"{policy_name} = {policy_source}\n"
            f"{quantum_name} = {decimal_type}(1).scaleb(-{policy_name}.scale)\n"
            f"{output_name} = {{}}\n"
            f"for {key_name}, {value_name} in {parameter}.items():\n"
            f"    if {value_name} is None:\n        continue\n"
            f"    if isinstance({value_name}, {decimal_type}):\n"
            f"        with {policy_name}.arithmetic_context():\n"
            f"            {value_name} = {policy_name}.normalize({value_name}, "
            f"field_name={key_name}).quantize({quantum_name}, rounding={policy_name}.rounding)\n"
            f"    {output_name}[{key_name}] = {value_name}\n"
            f"return {output_name}\n"
        ).body
        actual = [policy_assignment, quantum_assignment, output_assignment, loop, result]
        return ast.dump(ast.Module(body=actual, type_ignores=[])) == ast.dump(
            ast.Module(body=expected, type_ignores=[])
        )

    def helper_returns_immutable_amount(self, function: ast.FunctionDef, parameter: str) -> bool:
        """Prove read-only helpers return normalized Decimal/None, not hidden aliases."""
        saved_aliases = self.aliases.copy()
        scalar_names: set[str] = set()
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ):
            self.aliases[argument.arg] = None
        self.aliases[parameter] = "@output"

        def normalized(node: ast.AST | None) -> bool:
            return (
                isinstance(node, ast.Call)
                and self.symbol(node.func) == f"{self.policy}.normalize"
                and len(node.args) == 1
                and len(node.keywords) == 1
                and node.keywords[0].arg == "field_name"
            )

        def readonly(node: ast.AST) -> bool:
            for child in ast.walk(node):
                if isinstance(
                    child,
                    (
                        ast.NamedExpr,
                        ast.Lambda,
                        ast.Await,
                        ast.Yield,
                        ast.YieldFrom,
                        ast.ListComp,
                        ast.SetComp,
                        ast.DictComp,
                        ast.GeneratorExp,
                    ),
                ):
                    return False
                if isinstance(child, ast.Call) and not (
                    normalized(child)
                    or (
                        self.symbol(child.func) == "@output.get"
                        and len(child.args) in (1, 2)
                        and not any(isinstance(value, ast.Starred) for value in child.args)
                        and not child.keywords
                    )
                ):
                    return False
            return True

        def immutable(node: ast.AST | None) -> bool:
            return (
                isinstance(node, ast.Constant)
                and node.value is None
                or isinstance(node, ast.Name)
                and node.id in scalar_names
                or normalized(node)
                or isinstance(node, ast.IfExp)
                and immutable(node.body)
                and immutable(node.orelse)
            )

        try:
            for index, statement in enumerate(function.body):
                if not readonly(statement):
                    return False
                if (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                ):
                    continue
                if (
                    isinstance(statement, ast.Assign)
                    and len(statement.targets) == 1
                    and isinstance(statement.targets[0], ast.Name)
                ):
                    name = statement.targets[0].id
                    if name in self.aliases:
                        return False
                    if self.symbol(statement.value) == self.policy:
                        self.aliases[name] = self.policy
                    elif normalized(statement.value):
                        scalar_names.add(name)
                        self.aliases[name] = None
                    else:
                        return False
                elif (
                    isinstance(statement, ast.If)
                    and not statement.orelse
                    and len(statement.body) == 1
                    and isinstance(statement.body[0], ast.Return)
                    and isinstance(statement.body[0].value, ast.Constant)
                    and statement.body[0].value.value is None
                ):
                    continue
                elif isinstance(statement, ast.Return):
                    return index == len(function.body) - 1 and immutable(statement.value)
                else:
                    return False
            return False
        finally:
            self.aliases = saved_aliases

    def calls_use_bound_output(self, statement: ast.AST) -> bool:
        for node in ast.walk(statement):
            if isinstance(node, (ast.NamedExpr, ast.Await, ast.Yield, ast.YieldFrom)):
                return False
            if not isinstance(node, ast.Call):
                continue
            function = self.symbol(node.func)
            protected_arguments = {
                self.symbol(value)
                for argument in [*node.args, *(item.value for item in node.keywords)]
                for value in ast.walk(argument)
                if isinstance(value, ast.expr)
            } & {
                "@output",
                "@decoded",
                "@receipt_input",
                "@canonical_output",
                "@expected_policy",
                self.policy,
            }
            trusted = {
                f"{CALCULATION_LINEAGE_MODULE}.calculation_lineage_from_payload",
                f"{CALCULATION_LINEAGE_MODULE}.calculation_lineage_binds_output",
                f"{self.policy}.lineage_identity",
                *self.covered,
            }
            if protected_arguments and function not in trusted:
                return False
            if function in self.covered:
                parameters, output_parameter = self.covered_parameters[function]
                if len(node.args) > len(parameters) or any(
                    isinstance(value, ast.Starred) for value in node.args
                ):
                    return False
                arguments = dict(zip(parameters, node.args))
                for item in node.keywords:
                    if item.arg not in parameters or item.arg in arguments:
                        return False
                    arguments[item.arg] = item.value
                if (
                    output_parameter not in arguments
                    or self.symbol(arguments[output_parameter]) != "@output"
                ):
                    return False
                if function != self.specification["output_canonicalizer"] and not self.complete():
                    return False
            receiver = (
                self.symbol(node.func.value) if isinstance(node.func, ast.Attribute) else None
            )
            if receiver and any(
                receiver == root or receiver.startswith(root + ".")
                for root in (
                    "@output",
                    "@decoded",
                    "@canonical_output",
                    "@expected_policy",
                    self.policy,
                )
            ):
                if (
                    function == f"{self.policy}.lineage_identity"
                    and not node.args
                    and not node.keywords
                ):
                    continue
                # Mutating/opaque receiver calls are not evidence-preserving operations.
                return False
        return True

    def prove(self, module: ast.Module, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        if function.decorator_list or isinstance(function, ast.AsyncFunctionDef):
            return False
        canonicalizer = None
        amount_helpers: dict[str, ast.FunctionDef] = {}
        for statement in module.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    self.aliases[alias.asname or alias.name.split(".")[0]] = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
            elif isinstance(statement, ast.ImportFrom) and statement.level == 0:
                for alias in statement.names:
                    if alias.name == "*":
                        return False
                    self.aliases[alias.asname or alias.name] = f"{statement.module}.{alias.name}"
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.aliases[statement.name] = f"{self.path}::{statement.name}"
                callsite = f"{self.path}::{statement.name}"
                if callsite in self.covered:
                    parameters = [
                        argument.arg
                        for argument in (
                            *statement.args.posonlyargs,
                            *statement.args.args,
                            *statement.args.kwonlyargs,
                        )
                    ]
                    output_parameter = self.specification["output_parameter"]
                    if output_parameter not in parameters and len(parameters) == 1:
                        output_parameter = parameters[0]
                    if (
                        output_parameter not in parameters
                        or statement.args.vararg
                        or statement.args.kwarg
                        or statement.decorator_list
                        or isinstance(statement, ast.AsyncFunctionDef)
                        or callsite in self.covered_parameters
                    ):
                        return False
                    self.covered_parameters[callsite] = (parameters, output_parameter)
                    if callsite == self.specification["output_canonicalizer"]:
                        canonicalizer = statement
                    else:
                        amount_helpers[callsite] = statement
            else:
                # Later module assignments/classes/control flow may shadow imports.
                for node in ast.walk(statement):
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                        self.aliases[node.id] = None
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        for alias in node.names:
                            self.aliases[alias.asname or alias.name.split(".")[0]] = None
                if isinstance(statement, ast.ClassDef):
                    self.aliases[statement.name] = None
        if self.covered != set(self.covered_parameters):
            return False
        if canonicalizer is None or not self.canonicalizer_projects_input(
            canonicalizer, self.covered_parameters[self.specification["output_canonicalizer"]][1]
        ):
            return False
        if not all(
            self.helper_returns_immutable_amount(helper, self.covered_parameters[callsite][1])
            for callsite, helper in amount_helpers.items()
        ):
            return False
        boundary_parameters = {
            argument.arg
            for argument in (
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            )
        }
        boundary_parameters.update(
            argument.arg for argument in (function.args.vararg, function.args.kwarg) if argument
        )
        if (
            not {self.specification["receipt_parameter"], self.specification["output_parameter"]}
            <= boundary_parameters
        ):
            return False
        for name in boundary_parameters:
            self.aliases[name] = None
        self.aliases[self.specification["receipt_parameter"]] = "@receipt_input"
        self.aliases[self.specification["output_parameter"]] = "@output"
        for index, statement in enumerate(function.body):
            if not self.calls_use_bound_output(statement):
                return False
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                continue
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                name = statement.targets[0].id
                symbol = self.symbol(statement.value)
                protected_roots = {
                    "@output",
                    "@decoded",
                    "@receipt_input",
                    "@canonical_output",
                    "@expected_policy",
                    self.policy,
                }
                contains_protected_alias = any(
                    self.symbol(node) in protected_roots
                    for node in ast.walk(statement.value)
                    if isinstance(node, ast.expr)
                )
                if (
                    contains_protected_alias
                    and symbol is None
                    and not (
                        isinstance(statement.value, ast.Call)
                        and self.symbol(statement.value.func) in self.covered
                    )
                ):
                    # Containers/closures/computed wrappers can hide a mutable alias.
                    return False
                if self.aliases.get(name) in {
                    "@decoded",
                    "@output",
                    "@receipt_input",
                    "@canonical_output",
                    "@expected_policy",
                    self.policy,
                } or (isinstance(statement.value, ast.Call) and symbol == "@decoded"):
                    self.facts.clear()
                self.aliases[name] = symbol
            elif (
                isinstance(statement, ast.If)
                and not statement.orelse
                and len(statement.body) == 1
                and isinstance(statement.body[0], ast.Raise)
            ):
                self.facts.update(self.rejection_facts(statement.test))
            elif isinstance(statement, ast.Return):
                return index == len(function.body) - 1 and self.complete()
            else:
                return False
        return False


def _verified_retained_boundary(
    repo_root: Path,
    callsite: str,
    constant: str,
    declaration: PolicyDeclaration,
    specification: dict[str, Any],
    covered: set[str],
) -> bool:
    path, name = callsite.split("::", maxsplit=1)
    module = ast.parse((repo_root / path).read_text(encoding="utf-8"))
    functions = [
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    return len(functions) == 1 and _RetainedVerificationProof(
        path, constant, declaration, specification, covered
    ).prove(module, functions[0])


def _retained_boundaries(
    repo_root: Path,
    constant: str,
    declaration: PolicyDeclaration,
    policy: dict[str, Any],
    call_graph: dict[str, set[str]],
    computed_gaps: set[str],
) -> tuple[set[str], list[str]]:
    specifications = policy.get("lineage_verification_boundaries", {})
    if not isinstance(specifications, dict) or list(specifications) != sorted(specifications):
        return set(), [f"{constant}: invalid retained-verification boundary specifications"]
    verified: set[str] = set()
    findings: list[str] = []
    required_keys = {
        "receipt_parameter",
        "output_parameter",
        "output_canonicalizer",
        "algorithm_id",
        "algorithm_version",
    }
    for boundary, specification in specifications.items():
        covered = set(policy.get("lineage_boundary_covered_callsites", {}).get(boundary, []))
        valid = (
            boundary in policy.get("lineage_boundary_callsites", [])
            and boundary in call_graph
            and isinstance(specification, dict)
            and set(specification) == required_keys
            and all(
                isinstance(specification[name], str) and specification[name].isidentifier()
                for name in ("receipt_parameter", "output_parameter")
            )
            and specification["receipt_parameter"] != specification["output_parameter"]
            and isinstance(specification["algorithm_id"], str)
            and bool(specification["algorithm_id"].strip())
            and type(specification["algorithm_version"]) is int
            and specification["algorithm_version"] > 0
            and isinstance(specification["output_canonicalizer"], str)
            and specification["output_canonicalizer"] in covered & computed_gaps
            and boundary not in policy.get("lineage_boundary_terminal_callsites", {})
        )
        if valid and _verified_retained_boundary(
            repo_root, boundary, constant, declaration, specification, covered
        ):
            verified.add(boundary)
        else:
            findings.append(f"{constant}: invalid retained-verification boundary at {boundary}")
    return verified, findings


@dataclass(frozen=True, slots=True)
class PolicyDeclaration:
    constant: str
    declaration_path: str
    name: str
    version: str
    precision: int
    scale: int
    working_precision: int
    rounding: str


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError("contract root must be an object")
    return payload


def _literal(call: ast.Call, keyword: str, default: object = None) -> object:
    for item in call.keywords:
        if item.arg == keyword:
            try:
                return ast.literal_eval(item.value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{keyword} must be a literal") from exc
    return default


def _authored_source_paths(repo_root: Path) -> tuple[Path, ...]:
    """Include new authored files but exclude packaging directories declared in .gitignore."""

    source_root = repo_root / "src"
    return tuple(
        path
        for path in sorted(source_root.rglob("*.py"))
        if "build" not in path.relative_to(source_root).parent.parts
    )


def _declarations(repo_root: Path) -> dict[str, PolicyDeclaration]:
    declarations: dict[str, PolicyDeclaration] = {}
    for path in _authored_source_paths(repo_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        constructor_aliases = {"CalculatedDecimalPolicy"}
        for statement in tree.body:
            if isinstance(statement, ast.ImportFrom):
                for imported in statement.names:
                    if imported.name == "CalculatedDecimalPolicy":
                        constructor_aliases.add(imported.asname or imported.name)
                continue
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            value = statement.value
            if (
                len(targets) == 1
                and isinstance(targets[0], ast.Name)
                and not isinstance(
                    value,
                    ast.Call,
                )
            ):
                target_name = targets[0].id
                is_constructor_alias = (
                    isinstance(value, ast.Name) and value.id in constructor_aliases
                ) or (isinstance(value, ast.Attribute) and value.attr == "CalculatedDecimalPolicy")
                if is_constructor_alias:
                    constructor_aliases.add(target_name)
                else:
                    constructor_aliases.discard(target_name)
                continue
            if (
                value is None
                or not isinstance(value, ast.Call)
                or not isinstance(value.func, (ast.Name, ast.Attribute))
            ):
                continue
            constructor = value.func.id if isinstance(value.func, ast.Name) else value.func.attr
            if constructor not in constructor_aliases:
                continue
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                raise ValueError(f"{path}: calculated policy must use one named assignment")
            constant = targets[0].id
            if constant in declarations:
                raise ValueError(f"duplicate calculated policy constant: {constant}")
            declaration = PolicyDeclaration(
                constant=constant,
                declaration_path=path.relative_to(repo_root).as_posix(),
                name=str(_literal(value, "name")),
                version=str(_literal(value, "version")),
                precision=int(_literal(value, "precision")),
                scale=int(_literal(value, "scale")),
                working_precision=int(_literal(value, "working_precision", 64)),
                rounding=str(_literal(value, "rounding", ROUND_HALF_EVEN)),
            )
            declarations[constant] = declaration
    return declarations


def _source_module(source_path: str) -> str:
    parts = list(Path(source_path).with_suffix("").parts)
    if not parts or parts[0] != "src":
        raise ValueError(f"calculated policy path must be below src/: {source_path}")
    if len(parts) >= 4 and parts[1] in {"libs", "services"}:
        parts = parts[3:]
    else:
        parts = parts[1:]
    if not parts:
        raise ValueError(f"calculated policy path must identify a module: {source_path}")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_parts(relative_path: str, module_name: str) -> list[str]:
    """Return the import package for a module, including package ``__init__`` files."""

    parts = module_name.split(".")
    return parts if Path(relative_path).name == "__init__.py" else parts[:-1]


def _usage(
    repo_root: Path,
    declarations: dict[str, PolicyDeclaration],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
]:
    constants = set(declarations)
    policy_modules = {
        constant: _source_module(declaration.declaration_path)
        for constant, declaration in declarations.items()
    }
    execution = {constant: set() for constant in constants}
    lineage = {constant: set() for constant in constants}
    control_flow_gaps = {constant: set() for constant in constants}
    terminal_control_flow_gaps = {constant: set() for constant in constants}
    for path in _authored_source_paths(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        _UsageVisitor(
            relative_path=relative_path,
            constants=constants,
            policy_modules=policy_modules,
            execution=execution,
            lineage=lineage,
            control_flow_gaps=control_flow_gaps,
            terminal_control_flow_gaps=terminal_control_flow_gaps,
        ).visit(tree)
    return execution, lineage, control_flow_gaps, terminal_control_flow_gaps


def _call_graph(
    repo_root: Path,
    *,
    exact_calls_only: bool = False,
) -> dict[str, set[str]]:
    """Build import-aware callee-to-caller edges for boundary reachability."""

    trees: list[tuple[str, str, ast.Module]] = []
    callables_by_name: dict[str, set[str]] = {}
    properties_by_name: dict[str, set[str]] = {}
    callables_by_dotted_name: dict[str, set[str]] = {}
    properties_by_dotted_name: dict[str, set[str]] = {}
    local_callables: dict[tuple[str, str], set[str]] = {}
    local_properties: dict[tuple[str, str], set[str]] = {}
    for path in _authored_source_paths(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        module_name = _source_module(relative_path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        trees.append((relative_path, module_name, tree))
        callables_by_name.setdefault("<module>", set()).add(f"{relative_path}::<module>")

        class CallableCollector(ast.NodeVisitor):
            def __init__(self) -> None:
                self.scope: list[str] = []

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()

            def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                qualified_name = ".".join((*self.scope, node.name))
                callsite = f"{relative_path}::{qualified_name}"
                callables_by_name.setdefault(node.name, set()).add(callsite)
                callables_by_dotted_name.setdefault(f"{module_name}.{qualified_name}", set()).add(
                    callsite
                )
                local_callables.setdefault((relative_path, node.name), set()).add(callsite)
                if any(
                    isinstance(decorator, ast.Name) and decorator.id == "property"
                    for decorator in node.decorator_list
                ):
                    properties_by_name.setdefault(node.name, set()).add(callsite)
                    properties_by_dotted_name.setdefault(
                        f"{module_name}.{qualified_name}", set()
                    ).add(callsite)
                    local_properties.setdefault((relative_path, node.name), set()).add(callsite)
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()

            visit_FunctionDef = _visit_function
            visit_AsyncFunctionDef = _visit_function

        CallableCollector().visit(tree)

    graph: dict[str, set[str]] = {
        callsite: set() for callsites in callables_by_name.values() for callsite in callsites
    }
    # Resolve package re-exports before collecting calls so `from package import helper` points
    # back to the defining callable instead of disappearing from the graph.
    changed = True
    while changed:
        changed = False
        for relative_path, module_name, tree in trees:
            package_parts = _package_parts(relative_path, module_name)
            for statement in tree.body:
                if not isinstance(statement, ast.ImportFrom):
                    continue
                imported_module_parts = package_parts[:]
                if statement.level:
                    imported_module_parts = imported_module_parts[
                        : len(imported_module_parts) - (statement.level - 1)
                    ]
                else:
                    imported_module_parts = []
                if statement.module:
                    imported_module_parts.extend(statement.module.split("."))
                imported_module = ".".join(imported_module_parts)
                for alias in statement.names:
                    if alias.name == "*":
                        continue
                    targets = callables_by_dotted_name.get(f"{imported_module}.{alias.name}", set())
                    exported_name = alias.asname or alias.name
                    exported_key = f"{module_name}.{exported_name}"
                    existing = callables_by_dotted_name.setdefault(exported_key, set())
                    before = len(existing)
                    existing.update(targets)
                    changed = changed or len(existing) != before
    for relative_path, module_name, tree in trees:
        module_aliases: dict[str, str] = {}
        symbol_aliases: dict[str, str] = {}
        package_parts = _package_parts(relative_path, module_name)
        for statement in tree.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    root_name = alias.name.split(".")[0]
                    module_aliases[alias.asname or root_name] = (
                        alias.name if alias.asname else root_name
                    )
            elif isinstance(statement, ast.ImportFrom):
                imported_module_parts = package_parts[:]
                if statement.level:
                    imported_module_parts = imported_module_parts[
                        : len(imported_module_parts) - (statement.level - 1)
                    ]
                else:
                    imported_module_parts = []
                if statement.module:
                    imported_module_parts.extend(statement.module.split("."))
                imported_module = ".".join(imported_module_parts)
                for alias in statement.names:
                    if alias.name != "*":
                        symbol_aliases[alias.asname or alias.name] = (
                            f"{imported_module}.{alias.name}"
                        )

        class CallCollector(ast.NodeVisitor):
            def __init__(self) -> None:
                self.scope: list[str] = []
                self.typed_names: list[dict[str, str]] = []

            @property
            def caller(self) -> str:
                qualified_name = ".".join(self.scope) if self.scope else "<module>"
                return f"{relative_path}::{qualified_name}"

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()

            def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                self.scope.append(node.name)
                annotations: dict[str, str] = {}
                for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                    resolved = self._resolve_annotation(argument.annotation)
                    if resolved is not None:
                        annotations[argument.arg] = resolved
                self.typed_names.append(annotations)
                self.generic_visit(node)
                self.typed_names.pop()
                self.scope.pop()

            visit_FunctionDef = _visit_function
            visit_AsyncFunctionDef = _visit_function

            @staticmethod
            def _attribute_parts(expression: ast.Attribute) -> list[str] | None:
                parts = [expression.attr]
                value = expression.value
                while isinstance(value, ast.Attribute):
                    parts.append(value.attr)
                    value = value.value
                if not isinstance(value, ast.Name):
                    return None
                parts.append(value.id)
                return list(reversed(parts))

            def _resolve_name(self, name: str) -> set[str]:
                imported = symbol_aliases.get(name)
                if imported is not None:
                    return callables_by_dotted_name.get(imported, set())
                local = local_callables.get((relative_path, name), set())
                if local:
                    return local
                candidates = callables_by_name.get(name, set())
                return candidates if len(candidates) == 1 else set()

            def _resolve_annotation(self, annotation: ast.expr | None) -> str | None:
                if isinstance(annotation, ast.Name):
                    return symbol_aliases.get(annotation.id, f"{module_name}.{annotation.id}")
                if isinstance(annotation, ast.Attribute):
                    parts = self._attribute_parts(annotation)
                    if parts:
                        imported_root = module_aliases.get(parts[0]) or symbol_aliases.get(parts[0])
                        if imported_root is not None:
                            return ".".join((imported_root, *parts[1:]))
                return None

            def _resolve_attribute(
                self,
                expression: ast.Attribute,
                *,
                properties: bool = False,
            ) -> set[str]:
                parts = self._attribute_parts(expression)
                dotted_index = properties_by_dotted_name if properties else callables_by_dotted_name
                local_index = local_properties if properties else local_callables
                name_index = properties_by_name if properties else callables_by_name
                if parts:
                    root = parts[0]
                    imported_root = module_aliases.get(root) or symbol_aliases.get(root)
                    if imported_root is not None:
                        dotted_name = ".".join((imported_root, *parts[1:]))
                        return dotted_index.get(dotted_name, set())
                    if len(parts) == 2:
                        for typed_scope in reversed(self.typed_names):
                            annotated_type = typed_scope.get(root)
                            if annotated_type is not None:
                                typed_targets = dotted_index.get(
                                    f"{annotated_type}.{parts[1]}",
                                    set(),
                                )
                                if typed_targets or exact_calls_only:
                                    return typed_targets
                name = expression.attr
                if parts and parts[0] in {"self", "cls"} and len(parts) == 2:
                    local = local_index.get((relative_path, name), set())
                    if local:
                        return local
                if exact_calls_only:
                    # Bare attribute dispatch is runtime-selected. Keep it in the
                    # conservative reachability graph, but do not use it as proof
                    # that a governed helper has an independent direct caller.
                    return set()
                candidates = name_index.get(name, set())
                # An attribute call can be protocol/interface dispatch. Its receiver
                # is runtime-selected, so every same-named method is a possible
                # callee; directionality still prevents sibling/common-helper paths.
                return candidates

            def _connect(self, callees: set[str]) -> None:
                graph.setdefault(self.caller, set())
                for callee in callees:
                    graph[callee].add(self.caller)

            def visit_Call(self, node: ast.Call) -> None:
                if isinstance(node.func, ast.Name):
                    self._connect(self._resolve_name(node.func.id))
                elif isinstance(node.func, ast.Attribute):
                    self._connect(self._resolve_attribute(node.func))
                self.generic_visit(node)

            def visit_Attribute(self, node: ast.Attribute) -> None:
                if isinstance(node.ctx, ast.Load):
                    self._connect(self._resolve_attribute(node, properties=True))
                self.generic_visit(node)

        CallCollector().visit(tree)
    return graph


def _call_graph_reaches(
    graph: dict[str, set[str]],
    *,
    source: str,
    target: str,
) -> bool:
    if source not in graph or target not in graph:
        return False
    pending = [source]
    visited: set[str] = set()
    while pending:
        callsite = pending.pop()
        if callsite == target:
            return True
        if callsite in visited:
            continue
        visited.add(callsite)
        pending.extend(graph[callsite] - visited)
    return False


def _call_graph_escapes_boundary(
    caller_graph: dict[str, set[str]],
    *,
    source: str,
    boundaries: set[str],
    classified_terminals: set[str],
) -> bool:
    """Return whether any exact caller branch terminates outside a boundary.

    Exact import/name/self/typed-parameter dispatch is followed branch by branch. A cross-module
    leaf or cycle must reach one of this arithmetic callsite's assigned boundaries, unless the
    contract classifies that exact leaf as sibling-owned dataflow or read-only verification.
    """

    if source not in caller_graph or not boundaries:
        return True

    source_path = source.split("::", maxsplit=1)[0]

    def escapes(
        callsite: str,
        active_path: frozenset[str],
        crossed_module: bool,
    ) -> bool:
        if callsite in boundaries:
            return False
        if callsite in active_path:
            return crossed_module
        if callsite in classified_terminals:
            return False

        callers = caller_graph.get(callsite, set())
        if callers:
            next_path = active_path | {callsite}
            return any(
                escapes(
                    caller,
                    next_path,
                    crossed_module or caller.split("::", maxsplit=1)[0] != source_path,
                )
                for caller in callers
            )

        # Existing same-module calculation helpers are classified as part of their
        # declared owner boundary. Once a path leaves that module, an unclassified
        # terminal is an escape even if a separate sibling reaches the boundary.
        return crossed_module

    return escapes(source, frozenset(), False)


class _UsageVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        relative_path: str,
        constants: set[str],
        policy_modules: dict[str, str],
        execution: dict[str, set[str]],
        lineage: dict[str, set[str]],
        control_flow_gaps: dict[str, set[str]],
        terminal_control_flow_gaps: dict[str, set[str]],
    ) -> None:
        self._relative_path = relative_path
        self._constants = constants
        self._policy_modules = policy_modules
        self._execution = execution
        self._lineage = lineage
        self._control_flow_gaps = control_flow_gaps
        self._terminal_control_flow_gaps = terminal_control_flow_gaps
        self._scope: list[str] = []
        self._policy_aliases: list[dict[str, str | None]] = [{}]
        self._lineage_identity_aliases: list[dict[str, str | None]] = [{}]
        self._execution_method_aliases: list[dict[str, str | None]] = [{}]
        self._lineage_builder_aliases: list[dict[str, str | None]] = [{}]
        self._branch_usage: list[tuple[set[str], set[str]]] = []

    @property
    def _callsite(self) -> str:
        scope = ".".join(self._scope) if self._scope else "<module>"
        return f"{self._relative_path}::{scope}"

    def _visit_scope(
        self,
        node: ast.AST,
        name: str,
        *,
        shadowed_names: set[str] | None = None,
        policy_bindings: dict[str, str] | None = None,
    ) -> None:
        shadows = shadowed_names or set()
        self._scope.append(name)
        self._policy_aliases.append(dict.fromkeys(shadows))
        self._lineage_identity_aliases.append(dict.fromkeys(shadows))
        self._execution_method_aliases.append(dict.fromkeys(shadows))
        self._lineage_builder_aliases.append(dict.fromkeys(shadows))
        self._policy_aliases[-1].update(policy_bindings or {})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._visit_reachable_statements(node.body)
        elif isinstance(node, ast.Lambda):
            self.visit(node.body)
        else:
            self.generic_visit(node)
        self._lineage_builder_aliases.pop()
        self._execution_method_aliases.pop()
        self._lineage_identity_aliases.pop()
        self._policy_aliases.pop()
        self._scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scope(node, node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(
            node,
            node.name,
            shadowed_names=self._argument_names(node.args),
            policy_bindings=self._parameter_policy_bindings(node.args),
        )

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scope(
            node,
            node.name,
            shadowed_names=self._argument_names(node.args),
            policy_bindings=self._parameter_policy_bindings(node.args),
        )

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_scope(
            node,
            f"<lambda>@{node.lineno}",
            shadowed_names=self._argument_names(node.args),
            policy_bindings=self._parameter_policy_bindings(node.args),
        )

    @staticmethod
    def _argument_names(arguments: ast.arguments) -> set[str]:
        names = {
            argument.arg
            for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
        }
        if arguments.vararg is not None:
            names.add(arguments.vararg.arg)
        if arguments.kwarg is not None:
            names.add(arguments.kwarg.arg)
        return names

    def _parameter_policy_bindings(self, arguments: ast.arguments) -> dict[str, str]:
        bindings: dict[str, str] = {}
        positional = (*arguments.posonlyargs, *arguments.args)
        default_arguments = positional[len(positional) - len(arguments.defaults) :]
        for argument, default in zip(default_arguments, arguments.defaults, strict=True):
            constant = self._resolve_policy(default)
            if constant is not None:
                bindings[argument.arg] = constant
        for argument, default in zip(
            arguments.kwonlyargs,
            arguments.kw_defaults,
            strict=True,
        ):
            if default is None:
                continue
            constant = self._resolve_policy(default)
            if constant is not None:
                bindings[argument.arg] = constant
        return bindings

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        source_module = self._import_from_module(node)
        for imported in node.names:
            if imported.name == "*":
                self._shadow_visible_aliases()
                continue
            local_name = imported.asname or imported.name
            self._shadow_alias(local_name)
            if (
                imported.name in self._constants
                and source_module == self._policy_modules[imported.name]
            ):
                self._policy_aliases[-1][local_name] = imported.name
            if (
                node.module == CALCULATION_LINEAGE_MODULE
                or (node.level > 0 and node.module == "calculation_lineage")
            ) and imported.name == CALCULATION_LINEAGE_BUILDER:
                self._lineage_builder_aliases[-1][local_name] = "function"
            if node.module == "portfolio_common.domain" and imported.name == "calculation_lineage":
                self._lineage_builder_aliases[-1][local_name] = "module"

    def _import_from_module(self, node: ast.ImportFrom) -> str:
        if node.level == 0:
            return node.module or ""
        current_module = _source_module(self._relative_path)
        package_parts = current_module.split(".")[:-1]
        retained_parts = len(package_parts) - (node.level - 1)
        if retained_parts < 0:
            return ""
        resolved_parts = package_parts[:retained_parts]
        if node.module:
            resolved_parts.extend(node.module.split("."))
        return ".".join(resolved_parts)

    def visit_Import(self, node: ast.Import) -> None:
        for imported in node.names:
            local_name = imported.asname or imported.name.partition(".")[0]
            self._shadow_alias(local_name)
            if imported.name == CALCULATION_LINEAGE_MODULE and imported.asname:
                self._lineage_builder_aliases[-1][local_name] = "module"

    def visit_If(self, node: ast.If) -> None:
        predicate_usage = self._visit_control_expression(node.test)
        incoming = self._current_alias_state()
        body_state = self._visit_branch(
            incoming,
            node.body,
            initial_usage=predicate_usage,
        )
        else_state = self._visit_branch(
            incoming,
            node.orelse,
            initial_usage=predicate_usage,
        )
        self._restore_alias_state(self._join_alias_states(body_state, else_state))

    def visit_IfExp(self, node: ast.IfExp) -> None:
        predicate_usage = self._visit_control_expression(node.test)
        incoming = self._current_alias_state()
        body_state = self._visit_expression_branch(
            incoming,
            node.body,
            initial_usage=predicate_usage,
        )
        else_state = self._visit_expression_branch(
            incoming,
            node.orelse,
            initial_usage=predicate_usage,
        )
        self._restore_alias_state(self._join_alias_states(body_state, else_state))

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        incoming = self._current_alias_state()
        exit_states = [incoming]
        for value in node.values:
            exit_states.append(self._visit_expression_branch(incoming, value))
        self._restore_alias_state(self._join_alias_states(*exit_states))

    def _visit_expression_branch(
        self,
        incoming: tuple[dict[str, str | None], ...],
        expression: ast.expr,
        *,
        initial_usage: tuple[set[str], set[str]] | None = None,
    ) -> tuple[dict[str, str | None], ...]:
        self._restore_alias_state(incoming)
        execution, lineage = initial_usage or (set(), set())
        self._branch_usage.append((execution.copy(), lineage.copy()))
        self.visit(expression)
        execution, lineage = self._branch_usage.pop()
        for constant in execution - lineage:
            self._control_flow_gaps[constant].add(self._callsite)
        return self._current_alias_state()

    def _visit_control_expression(
        self,
        expression: ast.expr,
    ) -> tuple[set[str], set[str]]:
        self._branch_usage.append((set(), set()))
        self.visit(expression)
        return self._branch_usage.pop()

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop(node, self._visit_control_expression(node.iter))

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop(node, self._visit_control_expression(node.iter))

    def visit_While(self, node: ast.While) -> None:
        self._visit_loop(node, self._visit_control_expression(node.test))

    def _visit_loop(
        self,
        node: ast.For | ast.AsyncFor | ast.While,
        predicate_usage: tuple[set[str], set[str]],
    ) -> None:
        incoming = self._current_alias_state()
        body_state = self._visit_branch(
            incoming,
            node.body,
            initial_usage=predicate_usage,
        )
        else_state = self._visit_branch(
            incoming,
            node.orelse,
            initial_usage=predicate_usage,
        )
        # A loop can execute zero times, and a break can skip its else suite.
        self._restore_alias_state(self._join_alias_states(incoming, body_state, else_state))

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_try(node)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self._visit_try(node)

    def _visit_try(self, node: ast.Try | ast.TryStar) -> None:
        incoming = self._current_alias_state()
        body_state = self._visit_try_body(
            incoming,
            node.body,
            has_exceptional_exit=bool(node.handlers),
        )
        completed_state = self._visit_branch(body_state, node.orelse) if node.orelse else body_state
        exit_states = [incoming, completed_state]
        for handler in node.handlers:
            self._restore_alias_state(incoming)
            if handler.type is not None:
                self.visit(handler.type)
            if handler.name is not None:
                self._shadow_alias(handler.name)
            self._branch_usage.append((set(), set()))
            for statement in handler.body:
                self.visit(statement)
                if self._statement_terminates(statement):
                    break
            execution, lineage = self._branch_usage.pop()
            for constant in execution - lineage:
                self._control_flow_gaps[constant].add(self._callsite)
            exit_states.append(self._current_alias_state())
        self._restore_alias_state(self._join_alias_states(*exit_states))
        self._visit_reachable_statements(node.finalbody)

    def _visit_try_body(
        self,
        incoming: tuple[dict[str, str | None], ...],
        statements: list[ast.stmt],
        *,
        has_exceptional_exit: bool,
    ) -> tuple[dict[str, str | None], ...]:
        self._restore_alias_state(incoming)
        self._branch_usage.append((set(), set()))
        prior_execution: set[str] = set()
        prior_lineage: set[str] = set()
        for index, statement in enumerate(statements):
            if index > 0 and has_exceptional_exit:
                for constant in prior_execution - prior_lineage:
                    self._terminal_control_flow_gaps[constant].add(self._callsite)
            self._branch_usage.append((set(), set()))
            self.visit(statement)
            statement_execution, statement_lineage = self._branch_usage.pop()
            prior_execution.update(statement_execution)
            prior_lineage.update(statement_lineage)
            if self._statement_terminates(statement):
                break
        execution, lineage = self._branch_usage.pop()
        for constant in execution - lineage:
            gaps = (
                self._terminal_control_flow_gaps
                if self._branch_terminates(statements)
                else self._control_flow_gaps
            )
            gaps[constant].add(self._callsite)
        return self._current_alias_state()

    def visit_Match(self, node: ast.Match) -> None:
        subject_usage = self._visit_control_expression(node.subject)
        incoming = self._current_alias_state()
        exit_states = [self._visit_branch(incoming, [], initial_usage=subject_usage)]
        for case in node.cases:
            self._restore_alias_state(incoming)
            case_execution, case_lineage = (
                subject_usage[0].copy(),
                subject_usage[1].copy(),
            )
            if case.guard is not None:
                guard_execution, guard_lineage = self._visit_control_expression(case.guard)
                case_execution.update(guard_execution)
                case_lineage.update(guard_lineage)
            self._branch_usage.append((case_execution, case_lineage))
            for statement in case.body:
                self.visit(statement)
                if self._statement_terminates(statement):
                    break
            execution, lineage = self._branch_usage.pop()
            for constant in execution - lineage:
                self._control_flow_gaps[constant].add(self._callsite)
            exit_states.append(self._current_alias_state())
        # Include the incoming state because a match need not select a case.
        self._restore_alias_state(self._join_alias_states(*exit_states))

    def _shadow_alias(self, name: str) -> None:
        self._policy_aliases[-1][name] = None
        self._lineage_identity_aliases[-1][name] = None
        self._execution_method_aliases[-1][name] = None
        self._lineage_builder_aliases[-1][name] = None

    def _shadow_visible_aliases(self) -> None:
        visible_names = set(self._constants)
        for scoped_aliases in (
            self._policy_aliases,
            self._lineage_identity_aliases,
            self._execution_method_aliases,
            self._lineage_builder_aliases,
        ):
            visible_names.update(name for aliases in scoped_aliases for name in aliases)
        for name in visible_names:
            self._shadow_alias(name)

    def _visit_branch(
        self,
        incoming: tuple[dict[str, str | None], ...],
        statements: list[ast.stmt],
        *,
        initial_usage: tuple[set[str], set[str]] | None = None,
    ) -> tuple[dict[str, str | None], ...]:
        self._restore_alias_state(incoming)
        execution, lineage = initial_usage or (set(), set())
        self._branch_usage.append((execution.copy(), lineage.copy()))
        for statement in statements:
            self.visit(statement)
            if self._statement_terminates(statement):
                break
        execution, lineage = self._branch_usage.pop()
        for constant in execution - lineage:
            gaps = (
                self._terminal_control_flow_gaps
                if self._branch_terminates(statements)
                else self._control_flow_gaps
            )
            gaps[constant].add(self._callsite)
        return self._current_alias_state()

    @staticmethod
    def _branch_terminates(statements: list[ast.stmt]) -> bool:
        return any(
            isinstance(
                statement,
                (ast.Return, ast.Raise, ast.Break, ast.Continue),
            )
            for statement in statements
        )

    def _visit_reachable_statements(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self.visit(statement)
            if self._statement_terminates(statement):
                break

    @staticmethod
    def _statement_terminates(statement: ast.stmt) -> bool:
        return isinstance(
            statement,
            (ast.Return, ast.Raise, ast.Break, ast.Continue),
        )

    def _current_alias_state(self) -> tuple[dict[str, str | None], ...]:
        return (
            self._policy_aliases[-1].copy(),
            self._lineage_identity_aliases[-1].copy(),
            self._execution_method_aliases[-1].copy(),
            self._lineage_builder_aliases[-1].copy(),
        )

    def _restore_alias_state(
        self,
        state: tuple[dict[str, str | None], ...],
    ) -> None:
        (
            self._policy_aliases[-1],
            self._lineage_identity_aliases[-1],
            self._execution_method_aliases[-1],
            self._lineage_builder_aliases[-1],
        ) = (aliases.copy() for aliases in state)

    @staticmethod
    def _join_alias_states(
        *states: tuple[dict[str, str | None], ...],
    ) -> tuple[dict[str, str | None], ...]:
        missing = object()
        joined_state: list[dict[str, str | None]] = []
        for alias_maps in zip(*states, strict=True):
            joined: dict[str, str | None] = {}
            for name in set().union(*(aliases.keys() for aliases in alias_maps)):
                values = [aliases.get(name, missing) for aliases in alias_maps]
                first = values[0]
                if all(value == first for value in values[1:]):
                    # The union guarantees at least one branch contains the name,
                    # so equal branch values cannot all be the missing sentinel.
                    joined[name] = cast(str | None, first)
                else:
                    joined[name] = None
            joined_state.append(joined)
        return tuple(joined_state)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        policy_constant = self._resolve_policy(node.value)
        lineage_constant = self._resolve_lineage_identity(node.value)
        execution_constant = self._resolve_execution_method(node.value)
        builder_reference = self._resolve_lineage_builder_reference(node.value)
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            self._policy_aliases[-1][target.id] = policy_constant
            self._lineage_identity_aliases[-1][target.id] = lineage_constant
            self._execution_method_aliases[-1][target.id] = execution_constant
            self._lineage_builder_aliases[-1][target.id] = builder_reference

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        if node.value is None or not isinstance(node.target, ast.Name):
            return
        policy_constant = self._resolve_policy(node.value)
        self._policy_aliases[-1][node.target.id] = policy_constant
        lineage_constant = self._resolve_lineage_identity(node.value)
        self._lineage_identity_aliases[-1][node.target.id] = lineage_constant
        execution_constant = self._resolve_execution_method(node.value)
        self._execution_method_aliases[-1][node.target.id] = execution_constant
        self._lineage_builder_aliases[-1][node.target.id] = self._resolve_lineage_builder_reference(
            node.value
        )

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            constant = self._lookup_scoped_alias(
                node.func.id,
                self._execution_method_aliases,
            )
            if constant is not None:
                self._record_execution(constant)
        if isinstance(node.func, ast.Attribute):
            constant = self._resolve_policy(node.func.value)
            if constant is not None:
                if node.func.attr in EXECUTION_METHODS:
                    self._record_execution(constant)
        if self._resolve_lineage_builder_reference(node.func) == "function":
            for keyword in node.keywords:
                if keyword.arg != "numeric_output_policy":
                    continue
                constant = self._resolve_lineage_identity(keyword.value)
                if constant is not None:
                    self._record_lineage(constant)
        self.generic_visit(node)

    def _record_execution(self, constant: str) -> None:
        self._execution[constant].add(self._callsite)
        for execution, _ in self._branch_usage:
            execution.add(constant)

    def _record_lineage(self, constant: str) -> None:
        self._lineage[constant].add(self._callsite)
        if not self._branch_usage:
            # A builder after a control-flow join can bind every surviving output
            # path; a builder inside a sibling branch cannot.
            self._control_flow_gaps[constant].discard(self._callsite)
        for _, lineage in self._branch_usage:
            lineage.add(constant)

    def _resolve_lineage_builder_reference(self, expression: ast.expr) -> str | None:
        if isinstance(expression, ast.Name):
            return self._lookup_scoped_alias(
                expression.id,
                self._lineage_builder_aliases,
            )
        if not isinstance(expression, ast.Attribute):
            return None
        if expression.attr == CALCULATION_LINEAGE_BUILDER:
            if self._dotted_name(expression.value) == CALCULATION_LINEAGE_MODULE:
                return "function"
            if isinstance(expression.value, ast.Name):
                receiver = self._lookup_scoped_alias(
                    expression.value.id,
                    self._lineage_builder_aliases,
                )
                if receiver == "module":
                    return "function"
        return None

    @staticmethod
    def _dotted_name(expression: ast.expr) -> str | None:
        parts: list[str] = []
        current = expression
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.append(current.id)
        return ".".join(reversed(parts))

    def _resolve_lineage_identity(self, expression: ast.expr) -> str | None:
        if (
            isinstance(expression, ast.Call)
            and isinstance(expression.func, ast.Attribute)
            and expression.func.attr == "lineage_identity"
        ):
            return self._resolve_policy(expression.func.value)
        if isinstance(expression, ast.Name):
            return self._lookup_scoped_alias(
                expression.id,
                self._lineage_identity_aliases,
            )
        return None

    def _resolve_execution_method(self, expression: ast.expr) -> str | None:
        if isinstance(expression, ast.Attribute) and expression.attr in EXECUTION_METHODS:
            return self._resolve_policy(expression.value)
        if isinstance(expression, ast.Name):
            return self._lookup_scoped_alias(
                expression.id,
                self._execution_method_aliases,
            )
        return None

    @staticmethod
    def _lookup_scoped_alias(
        name: str,
        scopes: list[dict[str, str | None]],
    ) -> str | None:
        for aliases in reversed(scopes):
            if name in aliases:
                return aliases[name]
        return None

    def _resolve_policy(self, receiver: ast.expr) -> str | None:
        if isinstance(receiver, ast.Name):
            for aliases in reversed(self._policy_aliases):
                if receiver.id in aliases:
                    return aliases[receiver.id]
            return receiver.id if receiver.id in self._constants else None
        if isinstance(receiver, ast.Attribute) and receiver.attr in self._constants:
            return receiver.attr
        return None


def evaluate(repo_root: Path, contract_path: Path) -> tuple[str, ...]:
    payload = _load_contract(contract_path)
    findings: list[str] = []
    if not _authored_source_paths(repo_root):
        findings.append("no authored Python sources found below src/")
    if set(payload) != {"schema_version", "expected_inventory", "policies"}:
        findings.append("contract root must contain schema_version, expected_inventory, policies")
        return tuple(findings)
    if payload["schema_version"] != "1.0.0":
        findings.append("schema_version must be 1.0.0")
    policies = payload["policies"]
    if not isinstance(policies, dict):
        return (*findings, "policies must be an object")
    declarations = _declarations(repo_root)
    expected_inventory = payload["expected_inventory"]
    if not isinstance(expected_inventory, int) or isinstance(expected_inventory, bool):
        findings.append("expected_inventory must be an integer")
        return tuple(findings)
    if expected_inventory != len(policies):
        findings.append(
            f"expected_inventory={expected_inventory} does not match contract count={len(policies)}"
        )
    missing = sorted(set(declarations) - set(policies))
    stale = sorted(set(policies) - set(declarations))
    findings.extend(f"{constant}: missing contract classification" for constant in missing)
    findings.extend(f"{constant}: stale contract classification" for constant in stale)
    (
        execution,
        lineage,
        control_flow_gaps,
        terminal_control_flow_gaps,
    ) = _usage(repo_root, declarations)
    call_graph = _call_graph(repo_root)
    exact_call_graph = _call_graph(repo_root, exact_calls_only=True)
    for constant in sorted(set(declarations) & set(policies)):
        declaration = declarations[constant]
        policy = policies[constant]
        if (
            not isinstance(policy, dict)
            or not POLICY_KEYS.issubset(policy)
            or not set(policy).issubset(POLICY_KEYS | OPTIONAL_POLICY_KEYS)
        ):
            findings.append(
                f"{constant}: policy keys must include {sorted(POLICY_KEYS)} and may include "
                f"{sorted(OPTIONAL_POLICY_KEYS)}"
            )
            continue
        expected = {
            "declaration_path": declaration.declaration_path,
            "name": declaration.name,
            "version": declaration.version,
            "precision": declaration.precision,
            "scale": declaration.scale,
            "working_precision": declaration.working_precision,
            "rounding": declaration.rounding,
        }
        for field_name, actual in expected.items():
            if policy[field_name] != actual:
                findings.append(
                    f"{constant}.{field_name}: contract={policy[field_name]!r}, source={actual!r}"
                )
        for field_name in ("owner", "output_family"):
            if not isinstance(policy[field_name], str) or not policy[field_name].strip():
                findings.append(f"{constant}.{field_name}: must be nonblank")
        binding = policy["lineage_binding"]
        if binding not in LINEAGE_BINDINGS:
            findings.append(
                f"{constant}.lineage_binding: must be one of {sorted(LINEAGE_BINDINGS)}"
            )
        gap_callsites = policy["lineage_gap_callsites"]
        valid_gap_callsites = (
            isinstance(gap_callsites, list)
            and all(
                isinstance(callsite, str) and callsite.strip() and "::" in callsite
                for callsite in gap_callsites
            )
            and gap_callsites == sorted(set(gap_callsites))
        )
        if not valid_gap_callsites:
            findings.append(
                f"{constant}.lineage_gap_callsites: must be a sorted list of unique "
                "path::callable values"
            )
            continue
        execution_callsites = execution[constant]
        lineage_callsites = lineage[constant]
        boundary_callsites = policy.get("lineage_boundary_callsites", [])
        valid_boundary_callsites = (
            isinstance(boundary_callsites, list)
            and all(
                isinstance(callsite, str) and callsite.strip() and "::" in callsite
                for callsite in boundary_callsites
            )
            and boundary_callsites == sorted(set(boundary_callsites))
        )
        if not valid_boundary_callsites:
            findings.append(
                f"{constant}.lineage_boundary_callsites: must be a sorted list of unique "
                "path::callable values"
            )
            continue
        raw_boundary_coverage = policy.get("lineage_boundary_covered_callsites", {})
        valid_boundary_coverage = (
            isinstance(raw_boundary_coverage, dict)
            and list(raw_boundary_coverage) == sorted(raw_boundary_coverage)
            and all(
                isinstance(boundary, str)
                and boundary in boundary_callsites
                and isinstance(covered_callsites, list)
                and all(
                    isinstance(callsite, str) and callsite.strip() and "::" in callsite
                    for callsite in covered_callsites
                )
                and covered_callsites == sorted(set(covered_callsites))
                for boundary, covered_callsites in raw_boundary_coverage.items()
            )
        )
        if not valid_boundary_coverage:
            findings.append(
                f"{constant}.lineage_boundary_covered_callsites: must be an object keyed by "
                "declared boundary callsite with sorted unique path::callable value lists"
            )
            continue
        boundary_coverage = cast(dict[str, list[str]], raw_boundary_coverage)
        raw_boundary_terminals = policy.get("lineage_boundary_terminal_callsites", {})
        valid_boundary_terminals = (
            isinstance(raw_boundary_terminals, dict)
            and list(raw_boundary_terminals) == sorted(raw_boundary_terminals)
            and all(
                isinstance(boundary, str)
                and boundary in boundary_callsites
                and isinstance(terminals, dict)
                and list(terminals) == sorted(terminals)
                and all(
                    isinstance(callsite, str)
                    and callsite.strip()
                    and "::" in callsite
                    and reason
                    in {"lineage-bound-sibling-orchestrator", "read-only-lineage-verification"}
                    for callsite, reason in terminals.items()
                )
                for boundary, terminals in raw_boundary_terminals.items()
            )
        )
        if not valid_boundary_terminals:
            findings.append(
                f"{constant}.lineage_boundary_terminal_callsites: must be an object keyed by "
                "declared boundary callsite with sorted exact leaf callsite-to-reason objects"
            )
            continue
        boundary_terminals = cast(dict[str, dict[str, str]], raw_boundary_terminals)
        computed_gaps = (
            (execution_callsites - lineage_callsites)
            | control_flow_gaps[constant]
            | terminal_control_flow_gaps[constant]
        )
        retained_boundaries, retained_findings = _retained_boundaries(
            repo_root, constant, declaration, policy, exact_call_graph, computed_gaps
        )
        findings.extend(retained_findings)
        verified_boundaries = lineage_callsites | retained_boundaries
        unverified_boundaries = set(boundary_callsites) - verified_boundaries
        for callsite in sorted(unverified_boundaries):
            findings.append(
                f"{constant}: lineage boundary does not invoke the governed builder at {callsite}"
            )
        for boundary, terminals in boundary_terminals.items():
            if boundary not in boundary_coverage:
                findings.append(
                    f"{constant}: lineage dataflow terminals declared for boundary without "
                    f"coverage at {boundary}"
                )
            for terminal in sorted(terminals):
                if terminal not in exact_call_graph:
                    findings.append(f"{constant}: unknown lineage dataflow terminal at {terminal}")
                elif exact_call_graph[terminal]:
                    findings.append(
                        f"{constant}: lineage dataflow terminal has callers and is not terminal at "
                        f"{terminal}"
                    )
        covered_callsites: set[str] = set()
        assigned_boundaries: dict[str, set[str]] = {}
        for boundary, callsites in boundary_coverage.items():
            if boundary in unverified_boundaries:
                continue
            for callsite in callsites:
                if callsite not in computed_gaps:
                    findings.append(f"{constant}: stale lineage boundary coverage at {callsite}")
                    continue
                if not _call_graph_reaches(
                    call_graph,
                    source=callsite,
                    target=boundary,
                ):
                    findings.append(
                        f"{constant}: lineage boundary coverage has no call-graph path from "
                        f"{callsite} to {boundary}"
                    )
                    continue
                assigned_boundaries.setdefault(callsite, set()).add(boundary)

        for callsite, boundaries in assigned_boundaries.items():
            classified_terminals = {
                terminal
                for boundary in boundaries
                for terminal in boundary_terminals.get(boundary, {})
                if terminal in exact_call_graph and not exact_call_graph[terminal]
            }
            if _call_graph_escapes_boundary(
                exact_call_graph,
                source=callsite,
                boundaries=boundaries,
                classified_terminals=classified_terminals,
            ):
                findings.append(
                    f"{constant}: lineage boundary coverage has a caller path outside assigned "
                    f"boundaries from {callsite}"
                )
                continue
            covered_callsites.add(callsite)
        effective_gaps = computed_gaps - covered_callsites
        contract_gaps = set(gap_callsites)
        for callsite in sorted(effective_gaps - contract_gaps):
            findings.append(f"{constant}: unclassified lineage gap at {callsite}")
        for callsite in sorted(contract_gaps - effective_gaps):
            findings.append(f"{constant}: stale lineage gap at {callsite}")
        if not execution_callsites:
            findings.append(f"{constant}: no execution consumer found")
        if binding == "required" and (not verified_boundaries or effective_gaps):
            findings.append(f"{constant}: required lineage binding is incomplete")
        if binding == "partial" and (not verified_boundaries or not effective_gaps):
            findings.append(
                f"{constant}: partial lineage binding requires bound and unbound consumers"
            )
        if binding == "not-exposed" and verified_boundaries:
            findings.append(f"{constant}: not-exposed policy has a lineage binding")
    if len(declarations) != expected_inventory:
        findings.append(
            f"source inventory={len(declarations)} does not match expected={expected_inventory}"
        )
    return tuple(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    contract_path = (
        args.contract if args.contract.is_absolute() else repo_root / args.contract
    ).resolve()
    findings = evaluate(repo_root, contract_path)
    if findings:
        print("Calculated output policy guard failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    policy_count = _load_contract(contract_path)["expected_inventory"]
    print(f"Calculated output policy guard passed: {policy_count} policies classified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
