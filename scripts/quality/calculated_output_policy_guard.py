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


def _declarations(repo_root: Path) -> dict[str, PolicyDeclaration]:
    declarations: dict[str, PolicyDeclaration] = {}
    for path in sorted((repo_root / "src").rglob("*.py")):
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


def _usage(
    repo_root: Path,
    constants: set[str],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
]:
    execution = {constant: set() for constant in constants}
    lineage = {constant: set() for constant in constants}
    control_flow_gaps = {constant: set() for constant in constants}
    terminal_control_flow_gaps = {constant: set() for constant in constants}
    for path in sorted((repo_root / "src").rglob("*.py")):
        relative_path = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        _UsageVisitor(
            relative_path=relative_path,
            constants=constants,
            execution=execution,
            lineage=lineage,
            control_flow_gaps=control_flow_gaps,
            terminal_control_flow_gaps=terminal_control_flow_gaps,
        ).visit(tree)
    return execution, lineage, control_flow_gaps, terminal_control_flow_gaps


class _UsageVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        relative_path: str,
        constants: set[str],
        execution: dict[str, set[str]],
        lineage: dict[str, set[str]],
        control_flow_gaps: dict[str, set[str]],
        terminal_control_flow_gaps: dict[str, set[str]],
    ) -> None:
        self._relative_path = relative_path
        self._constants = constants
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
        for imported in node.names:
            if imported.name in self._constants:
                self._policy_aliases[-1][imported.asname or imported.name] = imported.name
            if (
                node.module == CALCULATION_LINEAGE_MODULE
                or (node.level > 0 and node.module == "calculation_lineage")
            ) and imported.name == CALCULATION_LINEAGE_BUILDER:
                self._lineage_builder_aliases[-1][imported.asname or imported.name] = "function"
            if node.module == "portfolio_common.domain" and imported.name == "calculation_lineage":
                self._lineage_builder_aliases[-1][imported.asname or imported.name] = "module"

    def visit_Import(self, node: ast.Import) -> None:
        for imported in node.names:
            if imported.name == CALCULATION_LINEAGE_MODULE and imported.asname:
                self._lineage_builder_aliases[-1][imported.asname] = "module"

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
            execution, lineage = self._branch_usage.pop()
            for constant in execution - lineage:
                self._control_flow_gaps[constant].add(self._callsite)
            exit_states.append(self._current_alias_state())
        self._restore_alias_state(self._join_alias_states(*exit_states))
        for statement in node.finalbody:
            self.visit(statement)

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
        return bool(statements) and isinstance(
            statements[-1],
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
    ) = _usage(repo_root, set(declarations))
    for constant in sorted(set(declarations) & set(policies)):
        declaration = declarations[constant]
        policy = policies[constant]
        if not isinstance(policy, dict) or set(policy) != POLICY_KEYS:
            findings.append(f"{constant}: policy keys must be {sorted(POLICY_KEYS)}")
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
        computed_gaps = (
            (execution_callsites - lineage_callsites)
            | control_flow_gaps[constant]
            | terminal_control_flow_gaps[constant]
        )
        contract_gaps = set(gap_callsites)
        for callsite in sorted(computed_gaps - contract_gaps):
            findings.append(f"{constant}: unclassified lineage gap at {callsite}")
        for callsite in sorted(contract_gaps - computed_gaps):
            findings.append(f"{constant}: stale lineage gap at {callsite}")
        if not execution_callsites:
            findings.append(f"{constant}: no execution consumer found")
        if binding == "required" and (not lineage_callsites or computed_gaps):
            findings.append(f"{constant}: required lineage binding is incomplete")
        if binding == "partial" and (not lineage_callsites or not computed_gaps):
            findings.append(
                f"{constant}: partial lineage binding requires bound and unbound consumers"
            )
        if binding == "not-exposed" and lineage_callsites:
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
