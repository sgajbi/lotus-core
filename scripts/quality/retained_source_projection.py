"""Structural proof of immutable finite FX bases and exact original-input projection.

This component inspects AST only. The owning validator retains import/symbol
binding, call-graph coverage, rejection facts and final acceptance. No inspected
source is executed and no function/source hash is an acceptance shortcut.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable, Mapping, TypeGuard, cast


def _is_docstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


class RetainedSourceProjection:
    """One bounded structural proof component, supplied explicit owner proof state."""

    def __init__(
        self,
        *,
        path: str,
        policy: str,
        aliases: Mapping[str, str | None],
        specification: Mapping[str, Any],
        repo_root: Path | None,
        module_name: Callable[[str], str],
        symbol: Callable[[ast.expr], str | None],
        lineage_module: str,
        immutable_basis_helpers: set[str],
        input_projection: Mapping[str, str],
    ) -> None:
        self.path, self.policy, self.repo_root = path, policy, repo_root
        self.aliases = dict(aliases)
        self.specification = dict(specification)
        self.module_name, self.symbol, self.lineage_module = module_name, symbol, lineage_module
        self.immutable_basis_helpers = frozenset(immutable_basis_helpers)
        self.input_projection = dict(input_projection)

    def structural_projection(self, node: ast.AST, roles: dict[str, str]) -> str:
        """Compare executable AST roles, not source text, annotations or source hashes."""
        aliases = self.aliases

        class Normalize(ast.NodeTransformer):
            def visit_Name(self, item: ast.Name) -> ast.Name:
                symbol = aliases.get(item.id)
                resolved = {
                    "decimal.Decimal": "D",
                    "decimal.InvalidOperation": "Invalid",
                    "typing.cast": "cast",
                    "dataclasses.dataclass": "dataclass",
                    "@basis_type": "Basis",
                    "@confirmation_type": "Confirmation",
                    "@rejection": "Reject",
                }.get(symbol or "")
                name = roles.get(item.id, resolved or item.id)
                if (
                    isinstance(item.ctx, ast.Load)
                    and item.id in aliases
                    and resolved is None
                    and item.id not in roles
                ):
                    name = "unproven_" + item.id
                return ast.Name(id=name, ctx=item.ctx)

            def visit_FunctionDef(self, item: ast.FunctionDef) -> ast.FunctionDef:
                item.name = roles.get(item.name, item.name)
                item.returns = None
                for arg in (*item.args.posonlyargs, *item.args.args, *item.args.kwonlyargs):
                    arg.arg, arg.annotation = roles.get(arg.arg, arg.arg), None
                item.body = [
                    statement
                    for statement in item.body
                    if not (
                        isinstance(statement, ast.Expr)
                        and isinstance(statement.value, ast.Constant)
                        and isinstance(statement.value.value, str)
                    )
                ]
                return cast(ast.FunctionDef, self.generic_visit(item))

            def visit_ClassDef(self, item: ast.ClassDef) -> ast.ClassDef:
                item.name = roles.get(item.name, item.name)
                item.body = [
                    statement
                    for statement in item.body
                    if not (
                        isinstance(statement, ast.Expr)
                        and isinstance(statement.value, ast.Constant)
                        and isinstance(statement.value.value, str)
                    )
                ]
                return cast(ast.ClassDef, self.generic_visit(item))

            def visit_Raise(self, item: ast.Raise) -> ast.Raise:
                # Error text is not authority. Only literal safe exception messages vary.
                if (
                    isinstance(item.exc, ast.Call)
                    and len(item.exc.args) == 1
                    and not item.exc.keywords
                ):
                    message = item.exc.args[0]
                    if isinstance(message, ast.Constant) and isinstance(message.value, str):
                        item.exc.args = [ast.Constant(value="invalid")]
                    elif isinstance(message, ast.JoinedStr) and not any(
                        isinstance(part, ast.Call) for part in ast.walk(message)
                    ):
                        item.exc.args = [ast.Constant(value="invalid")]
                return cast(ast.Raise, self.generic_visit(item))

        import copy

        return ast.dump(Normalize().visit(copy.deepcopy(node)))

    @staticmethod
    def _basis_class_roles(node: ast.ClassDef) -> dict[str, str]:
        """Discover alpha-equivalent names; the exact class template proves their use."""
        roles = {node.name: "Basis", "self": "self"}
        try:
            method = next(item for item in node.body if isinstance(item, ast.FunctionDef))
            roles[method.args.args[0].arg] = "self"
            loop = next(item for item in method.body if isinstance(item, ast.For))
            roles[cast(ast.Name, loop.target).id] = "field_name"
            assignment = next(item for item in loop.body if isinstance(item, ast.Assign))
            roles[cast(ast.Name, assignment.targets[0]).id] = "value"
        except (AttributeError, IndexError, StopIteration):
            pass
        return roles

    @staticmethod
    def _confirmation_class_roles(node: ast.ClassDef, roles: dict[str, str]) -> dict[str, str]:
        result = roles | {node.name: "Confirmation"}
        try:
            annotations = [item for item in node.body if isinstance(item, ast.AnnAssign)]
            for name in ast.walk(annotations[2].annotation):
                if isinstance(name, ast.Name) and name.id != "tuple":
                    result[name.id] = "CurrencyBasis"
        except IndexError:
            pass
        return result

    def immutable_projection_class(self, node: ast.ClassDef) -> str | None:
        """Full executable templates prove frozen finite fields, not annotations alone."""
        roles = self._basis_class_roles(node)
        basis = ast.parse("""
@dataclass(frozen=True, slots=True)
class Basis:
    source: D | None
    capital: D
    fx: D
    total: D
    def __post_init__(self):
        for field_name in ("source", "capital", "fx", "total"):
            value = getattr(self, field_name)
            if value is None and field_name == "source":
                continue
            if not isinstance(value, D):
                raise TypeError("invalid")
            if not value.is_finite():
                raise ValueError("invalid")
""").body[0]
        actual = self.structural_projection(node, roles)
        if actual == ast.dump(basis):
            return "@basis_type"
        confirmation = ast.parse("""
@dataclass(frozen=True, slots=True)
class Confirmation:
    local: Basis
    base: Basis
    confirmed_bases: tuple[CurrencyBasis, ...] = ()
    def __post_init__(self):
        if not isinstance(self.local, Basis) or not isinstance(self.base, Basis):
            raise TypeError("invalid")
""").body[0]
        roles = self._confirmation_class_roles(node, roles)
        if self.structural_projection(node, roles) == ast.dump(confirmation):
            return "@confirmation_type"
        return None

    @staticmethod
    def _basis_function_roles(function: ast.FunctionDef) -> dict[str, str] | None:
        parameters = [arg.arg for arg in function.args.args]
        try:
            first = next(item for item in function.body if not isinstance(item, ast.Expr))
            roles = dict(zip(parameters, ("raw", "output", "basis")))
            roles.update(
                {
                    function.name: "project",
                    cast(ast.Name, cast(ast.Assign, first).targets[0]).id: "source",
                }
            )
        except (AttributeError, IndexError, StopIteration):
            return None
        if len(roles) != 5 or len(set(roles.values())) != 5:
            return None
        return roles

    def helper_returns_immutable_basis(self, function: ast.FunctionDef) -> bool:
        """Match the complete finite-source/basis grammar after discovering local roles."""
        roles = self._basis_function_roles(function)
        if roles is None:
            return False
        expected = ast.parse("""
def project(raw, output, basis):
    source = raw.get(f"realized_fx_pnl_{basis}")
    if source is not None:
        if not isinstance(source, (str, D)):
            raise Reject("invalid")
        try:
            source = POLICY.normalize(D(source), field_name="fx_source")
        except (Invalid, ValueError, ArithmeticError):
            raise Reject("invalid") from None
        if source != output.get(f"realized_fx_pnl_{basis}"):
            raise Reject("invalid")
    try:
        return Basis(
            source=cast(D | None, source),
            capital=cast(D, output[f"realized_capital_pnl_{basis}"]),
            fx=cast(D, output[f"realized_fx_pnl_{basis}"]),
            total=cast(D, output[f"realized_total_pnl_{basis}"]),
        )
    except (KeyError, TypeError, ValueError):
        raise Reject("invalid") from None
""").body[0]
        policy_names = [name for name, symbol in self.aliases.items() if symbol == self.policy]
        roles.update({name: "POLICY" for name in policy_names})
        return self.structural_projection(function, roles) == ast.dump(expected)

    def _input_projection_declaration(self) -> tuple | None:
        """Load one declared source module; executable shape is proved separately."""
        specification = self.specification.get("input_verification")
        required = {"source_parameter", "source_projector", "input_builder", "presence_policy"}
        if not isinstance(specification, dict) or self.repo_root is None:
            return None
        if not all(
            (
                set(specification) == required,
                all(isinstance(value, str) and value for value in specification.values()),
            )
        ):
            return None
        try:
            if not specification["source_parameter"].isidentifier():
                return None
            builder_path, builder_name = specification["input_builder"].split("::")
            projector_path, projector_name = specification["source_projector"].split("::")
            if not all(
                (
                    builder_path == projector_path,
                    not Path(builder_path).is_absolute(),
                    ".." not in Path(builder_path).parts,
                )
            ):
                return None
            module = ast.parse((self.repo_root / builder_path).read_text(encoding="utf-8"))
            functions = {
                item.name: item for item in module.body if isinstance(item, ast.FunctionDef)
            }
            builder, projector = functions[builder_name], functions[projector_name]
        except (ValueError, OSError, SyntaxError, KeyError, AttributeError):
            return None
        return specification, module, builder_path, builder_name, projector_name, builder, projector

    @staticmethod
    def _register_symbol(aliases: dict, name: str, symbol: str | None) -> bool:
        if name == "*" or name in aliases:
            return False
        aliases[name] = symbol
        return True

    @classmethod
    def _register_import(cls, aliases: dict, statement: ast.ImportFrom) -> bool:
        allowed = {
            "collections.abc": {"Mapping"},
            "decimal": {"Decimal", "InvalidOperation"},
            "__future__": {"annotations"},
        }
        if statement.level or any(
            alias.name not in allowed.get(statement.module or "", set())
            for alias in statement.names
        ):
            return False
        return all(
            cls._register_symbol(
                aliases, alias.asname or alias.name, f"{statement.module}.{alias.name}"
            )
            for alias in statement.names
        )

    @classmethod
    def _register_literal(cls, declarations: dict, aliases: dict, statement: ast.Assign) -> bool:
        try:
            if len(statement.targets) != 1:
                return False
            name = cast(ast.Name, statement.targets[0]).id
            ast.literal_eval(statement.value)  # AST literals only, never execute module effects.
        except (AttributeError, ValueError, TypeError):
            return False
        if not cls._register_symbol(aliases, name, None):
            return False
        declarations[name] = statement.value
        return True

    @classmethod
    def _inert_presence_annotation(cls, node: ast.expr | None, aliases: dict) -> bool:
        """Closed grammar for the actual owners' inert type declarations."""
        if (
            node is None
            or isinstance(node, ast.Constant)
            and (node.value is None or isinstance(node.value, str))
        ):
            return True
        if isinstance(node, ast.Name):
            imported = aliases.get(node.id)
            return (
                imported in {"collections.abc.Mapping", "decimal.Decimal"}
                if node.id in aliases
                else node.id in {"dict", "str", "object", "int", "bool", "tuple", "list"}
            )
        if isinstance(node, ast.Subscript):
            if not isinstance(node.value, ast.Name):
                return False
            imported = aliases.get(node.value.id)
            generic = (
                imported == "collections.abc.Mapping"
                if node.value.id in aliases
                else node.value.id in {"dict", "tuple", "list"}
            )
            arguments = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            return generic and all(
                cls._inert_presence_annotation(argument, aliases) for argument in arguments
            )
        return False

    @classmethod
    def _inert_presence_function(cls, function: ast.FunctionDef, aliases: dict) -> bool:
        """Refuse executable definition headers, not arbitrary function bodies."""
        if function.decorator_list or getattr(function, "type_params", ()):
            return False
        parameters = [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
            *([function.args.vararg] if function.args.vararg else []),
            *([function.args.kwarg] if function.args.kwarg else []),
        ]
        if not all(
            cls._inert_presence_annotation(argument.annotation, aliases) for argument in parameters
        ) or not cls._inert_presence_annotation(function.returns, aliases):
            return False
        try:
            for default in [*function.args.defaults, *function.args.kw_defaults]:
                if default is not None:
                    ast.literal_eval(default)
        except (ValueError, TypeError, SyntaxError):
            return False
        return True

    def inert_retained_annotation(self, node: ast.expr | None) -> bool:
        """Closed type grammar for registered retained owners, resolved at definition time."""
        if (
            node is None
            or isinstance(node, ast.Constant)
            and (node.value is None or node.value is Ellipsis or isinstance(node.value, str))
        ):
            return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self.inert_retained_annotation(node.left) and self.inert_retained_annotation(
                node.right
            )
        supported = {
            "collections.abc.Mapping",
            "typing.Mapping",
            "typing.Literal",
            "decimal.Decimal",
            "datetime.datetime",
            "portfolio_common.events.TransactionEvent",
            "app.domain.transaction_economics.BookedTransactionEconomics",
            "app.domain.transaction_economics.FxPnlSourceEvidence",
            "@basis_type",
            "@confirmation_type",
            "@literal_type",
        }
        if isinstance(node, (ast.Name, ast.Attribute)):
            if isinstance(node, ast.Name) and node.id not in self.aliases:
                return node.id in {"dict", "str", "object", "int", "bool", "tuple", "list"}
            return self.symbol(node) in supported
        if isinstance(node, ast.Subscript):
            generic = self.symbol(node.value)
            approved = generic in {"collections.abc.Mapping", "typing.Mapping", "typing.Literal"}
            if isinstance(node.value, ast.Name) and node.value.id not in self.aliases:
                approved = node.value.id in {"dict", "tuple", "list"}
            arguments = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            return approved and all(self.inert_retained_annotation(arg) for arg in arguments)
        return False

    def inert_retained_function_header(
        self, function: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> bool:
        """No inspected owner code is executed; unrelated bodies are not a purity claim."""
        if function.decorator_list or getattr(function, "type_params", ()):
            return False
        arguments = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
        arguments += [arg for arg in (function.args.vararg, function.args.kwarg) if arg]
        if not all(self.inert_retained_annotation(arg.annotation) for arg in arguments):
            return False
        if not self.inert_retained_annotation(function.returns):
            return False
        try:
            for default in [*function.args.defaults, *function.args.kw_defaults]:
                if default is not None:
                    ast.literal_eval(default)
        except (ValueError, TypeError, SyntaxError):
            return False
        return True

    @classmethod
    def _presence_module_symbols(cls, module: ast.Module) -> tuple[dict, dict] | None:
        """Admit inert declarations only, with one fail-closed binding for every name."""
        declarations: dict[str, ast.expr] = {}
        aliases: dict[str, str | None] = {}
        for statement in module.body:
            if isinstance(statement, ast.ImportFrom):
                accepted = cls._register_import(aliases, statement)
            elif isinstance(statement, ast.Assign):
                accepted = cls._register_literal(declarations, aliases, statement)
            elif isinstance(statement, ast.FunctionDef):
                accepted = cls._inert_presence_function(
                    statement, aliases
                ) and cls._register_symbol(aliases, statement.name, None)
            else:
                accepted = _is_docstring(statement)
            if not accepted:
                return None
        return declarations, aliases

    @staticmethod
    def _presence_policy_roles(
        builder: ast.FunctionDef,
        projector: ast.FunctionDef,
        declarations: dict,
        presence_policy: str,
    ) -> tuple[str, str] | None:
        """Extract roles, requiring exact governed fields and declared policy values.

        Invalid AST shapes refuse here; the complete executable function shapes
        (including loops, writes, signatures and rejection control flow) are then
        compared by the single structural normalizer.
        """
        fields = tuple(
            f"realized_{component}_pnl_{basis}"
            for basis in ("local", "base")
            for component in ("capital", "fx", "total")
        )
        try:
            builder_body = [item for item in builder.body if not isinstance(item, ast.Expr)]
            projector_body = [item for item in projector.body if not isinstance(item, ast.Expr)]
            field_name = cast(ast.Name, cast(ast.For, builder_body[1]).iter).id
            if cast(ast.Name, cast(ast.For, projector_body[1]).iter).id != field_name:
                return None
            if ast.literal_eval(declarations[field_name]) != fields:
                return None
            result = cast(ast.Dict, cast(ast.Return, builder_body[-1]).value)
            policy_names = [
                cast(ast.Name, value).id
                for key, value in zip(result.keys, result.values)
                if isinstance(key, ast.Constant) and key.value == "source_presence_policy"
            ]
            if len(policy_names) != 1:
                return None
            policy_name = policy_names[0]
            if declarations[policy_name].value != presence_policy:
                return None
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            return None
        return field_name, policy_name

    @staticmethod
    def _presence_function_roles(
        function: ast.FunctionDef,
        arguments: list[str],
        expected_arguments: tuple[str, ...],
        output_name: str,
        field_name: str,
        policy_name: str,
    ) -> dict[str, str] | None:
        """Discover roles safely; only the subsequent full template proves behavior."""
        body = [item for item in function.body if not _is_docstring(item)]
        match body:
            case [
                ast.AnnAssign(target=ast.Name(id=result)),
                ast.For(target=ast.Name(id=index), body=statements),
                *_,
            ]:
                values = [
                    item.targets[0].id
                    for item in statements
                    if isinstance(item, ast.Assign)
                    and len(item.targets) == 1
                    and isinstance(item.targets[0], ast.Name)
                ]
            case _:
                return None
        if len(values) != 1 or len(arguments) != len(expected_arguments):
            return None
        roles = {
            function.name: "project",
            field_name: "FIELDS",
            policy_name: "PRESENCE_POLICY",
            result: output_name,
            index: "name",
            values[0]: "value",
        }
        roles.update(zip(arguments, expected_arguments))
        return roles if len(set(roles.values())) == len(roles) else None

    def _presence_functions_match(
        self,
        builder: ast.FunctionDef,
        projector: ast.FunctionDef,
        field_name: str,
        policy_name: str,
        external_aliases: dict,
    ) -> bool:
        builder_args = [arg.arg for arg in builder.args.kwonlyargs]
        projector_args = [arg.arg for arg in projector.args.args]
        saved = self.aliases
        self.aliases = external_aliases
        try:
            for function, arguments, output_name, template in (
                (
                    builder,
                    builder_args,
                    "original",
                    """
def project(*, source_values, booked_output):
    original: dict[str, object] = {}
    for name in FIELDS:
        if name not in source_values:
            raise ValueError("invalid")
        value = source_values[name]
        if value is not None and (not isinstance(value, D) or not value.is_finite()):
            raise ValueError("invalid")
        original[name] = {"present": value is not None, "value": value}
    return {"source_presence_policy": PRESENCE_POLICY, "original_pnl": original,
            "booked_economics": dict(booked_output)}
""",
                ),
                (
                    projector,
                    projector_args,
                    "values",
                    """
def project(raw_source):
    values: dict[str, object] = {}
    for name in FIELDS:
        value = raw_source.get(name)
        if value is not None:
            if not isinstance(value, (str, D)):
                raise ValueError("invalid")
            try:
                value = D(value)
            except Invalid:
                raise ValueError("invalid") from None
            if not value.is_finite():
                raise ValueError("invalid")
        values[name] = value
    return values
""",
                ),
            ):
                expected_arguments = (
                    ("source_values", "booked_output") if function is builder else ("raw_source",)
                )
                roles = self._presence_function_roles(
                    function, arguments, expected_arguments, output_name, field_name, policy_name
                )
                if roles is None:
                    return False
                if self.structural_projection(function, roles) != ast.dump(
                    ast.parse(template).body[0]
                ):
                    return False
        finally:
            self.aliases = saved
        return True

    def prove_original_input_projection(self) -> bool:
        """Prove the exact original-six policy through one structural proof pipeline."""
        declaration = self._input_projection_declaration()
        if declaration is None:
            return False
        specification, module, builder_path, builder_name, projector_name, builder, projector = (
            declaration
        )
        symbols = self._presence_module_symbols(module)
        if symbols is None:
            return False
        declarations, external_aliases = symbols
        roles = self._presence_policy_roles(
            builder, projector, declarations, specification["presence_policy"]
        )
        if roles is None or not self._presence_functions_match(
            builder, projector, *roles, external_aliases
        ):
            return False
        self.input_projection = {
            "builder": f"{self.module_name(builder_path)}.{builder_name}",
            "projector": f"{self.module_name(builder_path)}.{projector_name}",
            "source_parameter": specification["source_parameter"],
        }
        return True

    def _exact_call(
        self,
        node: ast.AST,
        symbol: str,
        positional_count: int,
        keyword_names: tuple[str, ...] = (),
    ) -> ast.Call | None:
        """Accept exactly the declared call shape, never star/extra/duplicate keywords."""
        if not isinstance(node, ast.Call):
            return None
        shape = (
            self.symbol(node.func) == symbol,
            len(node.args) == positional_count,
            len(node.keywords) == len(keyword_names),
            {keyword.arg for keyword in node.keywords} == set(keyword_names),
        )
        return node if all(shape) else None

    def _decoded_input_difference(self, node: ast.AST) -> TypeGuard[ast.Compare]:
        if not isinstance(node, ast.Compare):
            return False
        return all(
            (
                self.symbol(node.left) == "@decoded.input_content_hash",
                [type(operator) for operator in node.ops] == [ast.NotEq],
                len(node.comparators) == 1,
            )
        )

    def original_input_rejection(self, node: ast.AST) -> bool:
        """Trace decoded hash â†’ exact hash call â†’ proven builder â†’ original source."""
        if not self.input_projection or not self._decoded_input_difference(node):
            return False
        hashed = self._exact_call(
            node.comparators[0], f"{self.lineage_module}.canonical_content_hash", 1
        )
        if hashed is None:
            return False
        build = self._exact_call(
            hashed.args[0], self.input_projection["builder"], 0, ("source_values", "booked_output")
        )
        if build is None:
            return False
        values = {keyword.arg: keyword.value for keyword in build.keywords}
        if self.symbol(values["booked_output"]) != "@canonical_output":
            return False
        source = self._exact_call(values["source_values"], self.input_projection["projector"], 1)
        return source is not None and self.symbol(source.args[0]) == "@source_input"

    def _immutable_basis_return(self, node: ast.expr, basis: str) -> bool:
        if not isinstance(node, ast.Call):
            return False
        helper = self.symbol(node.func)
        if helper is None or helper not in self.immutable_basis_helpers:
            return False
        call = self._exact_call(node, helper, 3)
        if call is None:
            return False
        if not isinstance(call.args[2], ast.Constant):
            return False
        bound_arguments = (
            self.symbol(call.args[1]) == "@output",
            call.args[2].value == basis,
            not self.input_projection or self.symbol(call.args[0]) == "@source_input",
        )
        return all(bound_arguments)

    def immutable_confirmation_return(self, node: ast.expr | None) -> bool:
        if node is None:
            return False
        confirmation = self._exact_call(node, "@confirmation_type", 0, ("local", "base"))
        if confirmation is None:
            return False
        return all(
            self._immutable_basis_return(keyword.value, cast(str, keyword.arg))
            for keyword in confirmation.keywords
        )
