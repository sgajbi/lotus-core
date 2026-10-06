"""AST-only proof of exact numeric encoding and its bounded material consumers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable

from scripts.quality.retained_source_projection import RetainedSourceProjection

ENCODER = """
def encode(material):
    policy = POLICY
    output = dict(material)
    for name, value in material.items():
        if isinstance(value, D):
            exact(value, field_name=name)
            with policy.arithmetic_context():
                quantum = D(1).scaleb(-policy.scale)
                unsigned = value.copy_abs() if value.is_zero() else value
                output[name] = unsigned.quantize(quantum)
    return output
"""


def _definition_header(node, aliases) -> None:
    if any(
        not (
            isinstance(node, ast.ClassDef)
            and isinstance(decorator, ast.Call)
            and _symbol(decorator.func, aliases) == "dataclasses.dataclass"
        )
        for decorator in node.decorator_list
    ):
        raise ValueError("unproved decorator binding effects")
    headers = list(node.decorator_list)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        headers += [value for value in (*node.args.defaults, *node.args.kw_defaults) if value]
        headers += [
            arg.annotation
            for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            if arg.annotation
        ]
        if node.returns:
            headers.append(node.returns)
    else:
        headers += list(node.bases) + [keyword.value for keyword in node.keywords]
    for header in headers:
        for part in ast.walk(header):
            if isinstance(part, (ast.NamedExpr, ast.Lambda)):
                raise ValueError("effectful definition header")
            if isinstance(part, ast.Call) and not (
                isinstance(node, ast.ClassDef)
                and header in node.decorator_list
                and part is header
                and _symbol(part.func, aliases) == "dataclasses.dataclass"
                and not part.args
                and all(isinstance(keyword.value, ast.Constant) for keyword in part.keywords)
            ):
                raise ValueError("unproved definition-time call")


def _inert_assignment(node, aliases) -> None:
    for part in ast.walk(node):
        if isinstance(part, (ast.NamedExpr, ast.Lambda)):
            raise ValueError("unproved module assignment")
        if isinstance(part, ast.Call):
            symbol = _symbol(part.func, aliases)
            if symbol not in {
                "portfolio_common.domain.financial.precision.DecimalPrecisionPolicy",
                "portfolio_common.domain.financial.calculation_precision.CalculatedDecimalPolicy",
            } and not (
                isinstance(part.func, ast.Name)
                and part.func.id in {"tuple", "frozenset"}
                and part.func.id not in aliases
            ):
                raise ValueError("unproved module assignment call")


def _class_body(node, aliases) -> None:
    for statement in node.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _definition_header(statement, aliases)
        elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
            _inert_assignment(statement, aliases)
        elif isinstance(statement, ast.Pass) or (
            isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
        ):
            continue
        else:
            raise ValueError("unproved class-body effects")


def _load(root: Path, callsite: str, module_name: Callable[[str], str]):
    path, name = callsite.split("::", 1)
    tree = ast.parse((root / path).read_text(encoding="utf-8"))
    module = module_name(path)
    aliases: dict[str, str | None] = {}

    def bind(name, symbol):
        if name in aliases:
            raise ValueError("rebound module encoding authority")
        aliases[name] = symbol

    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _definition_header(item, aliases)
            bind(item.name, module + "." + item.name)
        elif isinstance(item, ast.ClassDef):
            _definition_header(item, aliases)
            _class_body(item, aliases)
            bind(item.name, None)
        elif isinstance(item, ast.ImportFrom):
            package = module.split(".")[:-1]
            prefix = package[: len(package) - item.level + 1] if item.level else []
            prefix += (item.module or "").split(".")
            for alias in item.names:
                if alias.name == "*":
                    raise ValueError("star imports cannot establish encoding authority")
                bind(alias.asname or alias.name, ".".join(prefix + [alias.name]))
        elif isinstance(item, ast.Import):
            for alias in item.names:
                bind(alias.asname or alias.name.split(".")[0], alias.name)
        elif isinstance(item, (ast.Assign, ast.AnnAssign)):
            _inert_assignment(item, aliases)
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    bind(target.id, None)
                else:
                    raise ValueError("unproved module binding target")
        elif isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant):
            continue
        else:
            raise ValueError("unsupported conditional or effectful module grammar")
    parts = name.split(".")
    body = tree.body
    for part in parts:
        matches = [
            item
            for item in body
            if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == part
        ]
        if len(matches) != 1:
            raise ValueError("missing or duplicate encoding proof callable")
        selected = matches[0]
        body = selected.body
    if not isinstance(selected, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise ValueError("encoding proof target must be callable")
    protected = {name for name, symbol in aliases.items() if symbol is not None}
    protected |= {"dict", "isinstance", "getattr", "sorted"}
    arguments = (*selected.args.posonlyargs, *selected.args.args, *selected.args.kwonlyargs)
    arguments += tuple(arg for arg in (selected.args.vararg, selected.args.kwarg) if arg)
    if any(argument.arg in protected for argument in arguments):
        raise ValueError("local argument shadows resolved encoding authority")
    for part in ast.walk(selected):
        if isinstance(part, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            raise ValueError("local rebinding grammar is unsupported")
        if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store) and part.id in protected:
            raise ValueError("local binding shadows resolved encoding authority")
        if (
            isinstance(part, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and part is not selected
            and part.name in protected
        ):
            raise ValueError("local definition shadows resolved encoding authority")
        if isinstance(part, ast.ExceptHandler) and part.name in protected:
            raise ValueError("exception binding shadows resolved encoding authority")
        if (
            isinstance(part, ast.Attribute)
            and isinstance(part.ctx, ast.Store)
            and _symbol(part.value, aliases)
        ):
            raise ValueError("mutation of resolved encoding authority")
    return selected, aliases


def _symbol(node: ast.expr, aliases: dict[str, str | None]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        owner = _symbol(node.value, aliases)
        return None if owner is None else owner + "." + node.attr
    return None


def _calls(function, symbol: str, aliases):
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and _symbol(node.func, aliases) == symbol
    ]


def _validator(root, policy_path, validator, module_name, precision, scale) -> bool:
    module = module_name(policy_path)
    if not validator.startswith(module + "."):
        return False
    node, aliases = _load(
        root, policy_path + "::" + validator.removeprefix(module + "."), module_name
    )
    body = [item for item in node.body if not isinstance(item, ast.Expr)]
    try:
        receiver = body[1].value.func.value.id
        parameter = node.args.args[0].arg
        field = node.args.kwonlyargs[0].arg
    except (AttributeError, IndexError):
        return False
    tree = ast.parse((root / policy_path).read_text(encoding="utf-8"))
    declarations = [
        item.value
        for item in tree.body
        if isinstance(item, ast.Assign)
        and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name)
        and item.targets[0].id == receiver
    ]
    if len(declarations) != 1 or not isinstance(declarations[0], ast.Call):
        return False
    declaration = declarations[0]
    if (
        _symbol(declaration.func, aliases)
        != "portfolio_common.domain.financial.precision.DecimalPrecisionPolicy"
    ):
        return False
    values = {keyword.arg: ast.literal_eval(keyword.value) for keyword in declaration.keywords}
    if values.get("precision") != precision or values.get("scale") != scale:
        return False
    roles = {node.name: "validate", parameter: "value", field: "field_name", receiver: "PRECISION"}
    proof = RetainedSourceProjection(
        path="",
        policy="",
        aliases=aliases,
        specification={},
        repo_root=None,
        module_name=module_name,
        symbol=lambda item: _symbol(item, aliases),
        lineage_module="",
        immutable_basis_helpers=set(),
        input_projection={},
    )
    expected = ast.parse(
        "def validate(value, *, field_name):\n"
        "    if value is None:\n        return None\n"
        "    return PRECISION.require_exact(value, field_name=field_name)\n"
    ).body[0]
    return proof.structural_projection(node, roles) == ast.dump(expected)


def _encoder(function, aliases, policy_symbol: str, validator: str) -> bool:
    if isinstance(function, ast.AsyncFunctionDef) or function.decorator_list:
        return False
    body = [
        item
        for item in function.body
        if not isinstance(item, ast.Expr)
        or not isinstance(item.value, ast.Constant)
        or not isinstance(item.value.value, str)
    ]
    try:
        policy = body[0].targets[0].id
        output = body[1].targets[0].id
        name, value = [item.id for item in body[2].target.elts]
        context = body[2].body[0].body[1]
        quantum = context.body[0].targets[0].id
        unsigned = context.body[1].targets[0].id
        roles = {
            function.name: "encode",
            function.args.args[0].arg: "material",
            policy: "policy",
            output: "output",
            name: "name",
            value: "value",
            quantum: "quantum",
            unsigned: "unsigned",
        }
    except (AttributeError, IndexError, TypeError):
        return False
    roles.update({name: "POLICY" for name, symbol in aliases.items() if symbol == policy_symbol})
    roles.update({name: "exact" for name, symbol in aliases.items() if symbol == validator})
    if not {"POLICY", "exact"} <= set(roles.values()):
        return False
    if any(name in aliases for name in ("dict", "isinstance")):
        return False
    proof = RetainedSourceProjection(
        path="",
        policy=policy_symbol,
        aliases=aliases,
        specification={},
        repo_root=None,
        module_name=lambda path: path,
        symbol=lambda node: _symbol(node, aliases),
        lineage_module="",
        immutable_basis_helpers=set(),
        input_projection={},
    )
    return proof.structural_projection(function, roles) == ast.dump(ast.parse(ENCODER).body[0])


def prove_encoding(
    root: Path,
    callsite: str,
    specification: dict,
    *,
    policy_symbol: str,
    policy_path: str,
    precision: int,
    scale: int,
    module_name: Callable[[str], str],
    callers: dict[str, set[str]],
    lineage: set[str],
) -> bool:
    """A declaration never exempts an unproved shape, unknown caller or mutable use."""
    try:
        if set(specification) != {"exact_validator", "consumers"} or not specification["consumers"]:
            return False
        if not _validator(
            root, policy_path, specification["exact_validator"], module_name, precision, scale
        ):
            return False
        function, aliases = _load(root, callsite, module_name)
        if not _encoder(function, aliases, policy_symbol, specification["exact_validator"]):
            return False
        consumers = specification["consumers"]
        if set(consumers) != callers.get(callsite, set()):
            return False
        encoder_symbol = module_name(callsite.split("::")[0]) + "." + function.name
        for consumer, kind in consumers.items():
            node, bindings = _load(root, consumer, module_name)
            calls = _calls(node, encoder_symbol, bindings)
            if len(calls) != 1:
                return False
            call = calls[0]
            if len(call.args) != 1 or call.keywords:
                return False
            if kind == "lineage-material":
                if (
                    not isinstance(call.args[0], ast.Name)
                    or consumer not in lineage
                    or not _lineage_material(node, call, bindings)
                ):
                    return False
            elif isinstance(kind, dict) and set(kind) == {"source_cut_reader"}:
                if not _source_cut_material(
                    root,
                    consumer,
                    node,
                    call,
                    bindings,
                    encoder_symbol,
                    kind["source_cut_reader"],
                    callers,
                    module_name,
                ):
                    return False
            else:
                return False
        return True
    except (OSError, SyntaxError, ValueError, AttributeError, KeyError, TypeError):
        return False


def _lineage_material(node, call, aliases) -> bool:
    assignments = [
        item for item in node.body if isinstance(item, ast.Assign) and item.value is call
    ]
    if (
        len(assignments) != 1
        or len(assignments[0].targets) != 1
        or not isinstance(assignments[0].targets[0], ast.Name)
    ):
        return False
    name = assignments[0].targets[0].id
    builders = _calls(
        node, "portfolio_common.domain.calculation_lineage.build_calculation_lineage", aliases
    )
    output_names = [
        part
        for builder in builders
        for keyword in builder.keywords
        if keyword.arg == "output_payload"
        for part in ast.walk(keyword.value)
        if isinstance(part, ast.Name) and part.id == name
    ]
    returns = [
        part
        for item in node.body
        if isinstance(item, ast.Return)
        for part in ast.walk(item)
        if isinstance(part, ast.Name) and part.id == name
    ]
    references = [part for part in ast.walk(node) if isinstance(part, ast.Name) and part.id == name]
    return len(output_names) == len(returns) == 1 and len(references) == 3


def _source_cut_material(
    root, consumer, node, call, bindings, encoder_symbol, reader, callers, module_name
) -> bool:
    body = [item for item in node.body if not isinstance(item, ast.Expr)]
    if (
        len(body) == 2
        and isinstance(body[0], ast.Assign)
        and isinstance(body[0].value, ast.Name)
        and isinstance(body[0].targets[0], ast.Tuple)
    ):
        body = body[1:]
    if (
        len(body) != 1
        or not isinstance(body[0], ast.Return)
        or not isinstance(body[0].value, ast.Dict)
    ):
        return False
    if sum(value is call for value in body[0].value.values) != 1 or callers.get(
        consumer, set()
    ) != {reader}:
        return False
    # Material projection may read attributes but cannot call arbitrary effectful code.
    allowed_symbols = {
        encoder_symbol,
        module_name(consumer.split("::")[0]) + ".transaction_receipt_output",
    }
    if "getattr" in bindings:
        return False
    if any(
        isinstance(part, ast.Call)
        and not (
            isinstance(part.func, ast.Name)
            and part.func.id == "getattr"
            or _symbol(part.func, bindings) in allowed_symbols
        )
        for part in ast.walk(node)
    ):
        return False
    owner, aliases = _load(root, reader, module_name)
    if "sorted" in aliases:
        return False
    projection_symbol = module_name(consumer.split("::")[0]) + "." + node.name
    projections = _calls(owner, projection_symbol, aliases)
    parents = {
        child: parent for parent in ast.walk(owner) for child in ast.iter_child_nodes(parent)
    }
    if len(projections) != 1:
        return False
    current = projections[0]
    while current in parents and not isinstance(current, ast.Assign):
        current = parents[current]
    if (
        not isinstance(current, ast.Assign)
        or not isinstance(current.value, ast.Call)
        or not isinstance(current.value.func, ast.Name)
        or current.value.func.id != "sorted"
    ):
        return False
    if len(current.targets) != 1 or not isinstance(current.targets[0], ast.Name):
        return False
    material = current.targets[0].id
    hashes = _calls(
        owner, "portfolio_common.domain.calculation_lineage.canonical_content_hash", aliases
    )
    usages = [
        part for part in ast.walk(owner) if isinstance(part, ast.Name) and part.id == material
    ]
    hash_usages = [
        part
        for hashed in hashes
        for part in ast.walk(hashed)
        if isinstance(part, ast.Name) and part.id == material
    ]
    return len(usages) == 2 and len(hash_usages) == 1
