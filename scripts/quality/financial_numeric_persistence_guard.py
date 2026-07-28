from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = Path("docs/standards/financial-numeric-persistence.v1.json")

_CANONICAL_PROFILES = {
    "finite": {"nullable": False, "sign": "signed"},
    "positive-finite": {"nullable": False, "sign": "positive"},
    "nonnegative-finite": {"nullable": False, "sign": "nonnegative"},
    "nullable-finite": {"nullable": True, "sign": "signed"},
    "nullable-positive-finite": {"nullable": True, "sign": "positive"},
    "nullable-nonnegative-finite": {"nullable": True, "sign": "nonnegative"},
}
_ROLLOUT_STATUSES = {"orm-enforced", "planned"}
_SPECIAL_NUMERIC_LITERALS = ("NaN", "Infinity", "-Infinity")
_SQLALCHEMY_NUMERIC_CONSTRUCTORS = {"Numeric", "NUMERIC", "DECIMAL", "ExactNumeric"}
_FINITE_CONSTRAINT_HELPER = "_finite_numeric_check_constraint"
_V2_CONTRACT_KEYS = {
    "schema_version",
    "model_path",
    "expected_inventory",
    "profiles",
    "rollout_statuses",
    "storage_shapes",
    "default_storage_shape",
    "exact_bind_enforcement",
    "storage_shape_overrides",
    "domain_families",
    "table_domain_families",
    "tables",
}
_STORAGE_SHAPE_KEYS = {"mode", "precision", "scale"}
_STORAGE_SHAPE_MODES = {"bounded", "exact-unbounded"}
_DOMAIN_FAMILY_KEYS = {"owner", "boundary_class"}
_BOUNDARY_CLASSES = {
    "api-command",
    "calculation-state",
    "control-policy",
    "reference-source",
}


class DuplicateContractKeyError(ValueError):
    pass


class UnsupportedNumericDeclarationError(ValueError):
    pass


@dataclass(frozen=True)
class NumericColumn:
    table: str
    column: str
    nullable: bool
    precision: int | None
    scale: int | None
    constructor: str
    check_constraints: tuple[str, ...]

    @property
    def identity(self) -> str:
        return f"{self.table}.{self.column}"

    @property
    def is_unbounded(self) -> bool:
        return self.precision is None and self.scale is None


@dataclass(frozen=True)
class GuardReport:
    findings: tuple[str, ...]
    numeric_column_count: int
    table_count: int
    bounded_numeric_count: int
    unbounded_numeric_count: int
    domain_family_count: int
    orm_enforced_count: int
    database_enforced_count: int
    planned_count: int


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateContractKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(payload, dict):
        raise ValueError("contract root must be an object")
    return payload


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _constant_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _extract_table_name(class_node: ast.ClassDef) -> str | None:
    for statement in class_node.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__tablename__"
            for target in statement.targets
        ):
            continue
        return _constant_string(statement.value)
    return None


def _extract_check_constraints(class_node: ast.ClassDef) -> tuple[str, ...]:
    checks: list[str] = []
    for node in ast.walk(class_node):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name == "CheckConstraint":
            if not node.args:
                continue
            expression = _constant_string(node.args[0])
            if expression is not None:
                checks.append(expression)
            continue
        if call_name != _FINITE_CONSTRAINT_HELPER:
            continue
        if len(node.args) < 2:
            raise UnsupportedNumericDeclarationError(
                f"{class_node.name}: {_FINITE_CONSTRAINT_HELPER} requires a name "
                "and at least one column"
            )
        constraint_name = _constant_string(node.args[0])
        column_names = tuple(_constant_string(argument) for argument in node.args[1:])
        if constraint_name is None or any(column is None for column in column_names):
            raise UnsupportedNumericDeclarationError(
                f"{class_node.name}: {_FINITE_CONSTRAINT_HELPER} arguments must be string literals"
            )
        values = ", ".join(f"'{value}'" for value in _SPECIAL_NUMERIC_LITERALS)
        checks.append(
            " AND ".join(
                f"CAST({column} AS TEXT) NOT IN ({values})"
                for column in column_names
                if column is not None
            )
        )
    return tuple(checks)


def _module_assignment(statement: ast.stmt) -> tuple[str, ast.expr | None] | None:
    if (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ):
        return statement.targets[0].id, statement.value
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return statement.target.id, statement.value
    return None


def _numeric_constructor_names(tree: ast.Module) -> frozenset[str]:
    constructors: set[str] = set()
    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom):
            continue
        if statement.module is None or not statement.module.startswith("sqlalchemy"):
            continue
        for imported in statement.names:
            if imported.name in _SQLALCHEMY_NUMERIC_CONSTRUCTORS:
                constructors.add(imported.asname or imported.name)
    return frozenset(constructors)


def _numeric_type_aliases(
    tree: ast.Module,
    *,
    constructors: frozenset[str],
) -> frozenset[str]:
    constructor_names = constructors | _SQLALCHEMY_NUMERIC_CONSTRUCTORS
    assignments = [
        assignment
        for statement in tree.body
        if (assignment := _module_assignment(statement)) is not None
    ]
    aliases = {
        name
        for name, value in assignments
        if (
            (isinstance(value, ast.Call) and _call_name(value.func) in constructor_names)
            or (isinstance(value, ast.Name) and value.id in constructor_names)
            or (isinstance(value, ast.Attribute) and _call_name(value) in constructor_names)
        )
    }
    changed = True
    while changed:
        changed = False
        for name, value in assignments:
            if isinstance(value, ast.Name) and value.id in aliases and name not in aliases:
                aliases.add(name)
                changed = True
    for name, value in assignments:
        if value is None or name in aliases:
            continue
        if any(
            isinstance(node, ast.Call) and _call_name(node.func) in constructor_names
            for node in ast.walk(value)
        ):
            raise UnsupportedNumericDeclarationError(
                f"{name}: unsupported indirect Numeric alias; assign Numeric(...) directly "
                "or extend the guard inventory"
            )
    return frozenset(aliases)


def _is_numeric_type(
    expression: ast.expr,
    *,
    constructors: frozenset[str],
    numeric_aliases: frozenset[str],
) -> bool:
    constructor_names = constructors | _SQLALCHEMY_NUMERIC_CONSTRUCTORS
    return (
        isinstance(expression, ast.Call)
        and _call_name(expression.func) in (constructor_names | numeric_aliases)
    ) or (
        isinstance(expression, ast.Name)
        and (expression.id in constructor_names or expression.id in numeric_aliases)
    )


def _integer_literal(
    node: ast.AST,
    *,
    declaration: str,
    field: str,
    minimum: int,
) -> int:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, int):
        raise UnsupportedNumericDeclarationError(
            f"{declaration}: Numeric {field} must be an integer literal"
        )
    if node.value < minimum:
        raise UnsupportedNumericDeclarationError(
            f"{declaration}: Numeric {field} must be at least {minimum}"
        )
    return node.value


def _numeric_shape_from_call(
    expression: ast.Call,
    *,
    declaration: str,
) -> tuple[int | None, int | None]:
    if len(expression.args) not in {0, 1, 2}:
        raise UnsupportedNumericDeclarationError(
            f"{declaration}: Numeric accepts at most precision and scale"
        )
    precision_node = expression.args[0] if expression.args else None
    scale_node = expression.args[1] if len(expression.args) == 2 else None
    for keyword in expression.keywords:
        if keyword.arg == "precision":
            if precision_node is not None:
                raise UnsupportedNumericDeclarationError(
                    f"{declaration}: Numeric precision is declared more than once"
                )
            precision_node = keyword.value
        elif keyword.arg == "scale":
            if scale_node is not None:
                raise UnsupportedNumericDeclarationError(
                    f"{declaration}: Numeric scale is declared more than once"
                )
            scale_node = keyword.value
        elif keyword.arg not in {"decimal_return_scale", "asdecimal"}:
            raise UnsupportedNumericDeclarationError(
                f"{declaration}: unsupported Numeric keyword {keyword.arg!r}"
            )
    if precision_node is None and scale_node is None:
        return None, None
    if precision_node is None or scale_node is None:
        raise UnsupportedNumericDeclarationError(
            f"{declaration}: bounded Numeric requires both precision and scale"
        )
    precision = _integer_literal(
        precision_node,
        declaration=declaration,
        field="precision",
        minimum=1,
    )
    scale = _integer_literal(
        scale_node,
        declaration=declaration,
        field="scale",
        minimum=0,
    )
    if scale > precision:
        raise UnsupportedNumericDeclarationError(
            f"{declaration}: Numeric scale must not exceed precision"
        )
    return precision, scale


def _numeric_alias_shapes(
    tree: ast.Module,
    *,
    constructors: frozenset[str],
    numeric_aliases: frozenset[str],
) -> dict[str, tuple[int | None, int | None]]:
    constructor_names = constructors | _SQLALCHEMY_NUMERIC_CONSTRUCTORS
    assignments = [
        assignment
        for statement in tree.body
        if (assignment := _module_assignment(statement)) is not None
    ]
    shapes: dict[str, tuple[int | None, int | None]] = {}
    unresolved = {name: value for name, value in assignments if name in numeric_aliases}
    while unresolved:
        progressed = False
        for name, value in tuple(unresolved.items()):
            if isinstance(value, ast.Call) and _call_name(value.func) in (
                constructor_names | numeric_aliases
            ):
                parent_name = _call_name(value.func)
                if parent_name in numeric_aliases and parent_name not in shapes and not value.args:
                    continue
                shapes[name] = (
                    _numeric_shape_from_call(value, declaration=name)
                    if value.args or value.keywords or parent_name in constructor_names
                    else shapes[parent_name]
                )
            elif isinstance(value, (ast.Name, ast.Attribute)):
                referenced_name = _call_name(value)
                if referenced_name in constructor_names:
                    shapes[name] = (None, None)
                elif referenced_name in shapes:
                    shapes[name] = shapes[referenced_name]
                else:
                    continue
            else:
                raise UnsupportedNumericDeclarationError(
                    f"{name}: unsupported Numeric alias declaration"
                )
            del unresolved[name]
            progressed = True
        if not progressed:
            names = ", ".join(sorted(unresolved))
            raise UnsupportedNumericDeclarationError(
                f"cannot resolve Numeric alias shape(s): {names}"
            )
    return shapes


def _numeric_type_expression(
    declaration: ast.Call,
    *,
    constructors: frozenset[str],
    numeric_aliases: frozenset[str],
) -> ast.expr | None:
    positional = [
        argument
        for argument in declaration.args
        if _is_numeric_type(
            argument,
            constructors=constructors,
            numeric_aliases=numeric_aliases,
        )
    ]
    keyword = [
        item.value
        for item in declaration.keywords
        if item.arg == "type_"
        and _is_numeric_type(
            item.value,
            constructors=constructors,
            numeric_aliases=numeric_aliases,
        )
    ]
    candidates = positional + keyword
    if not candidates:
        return None
    if len(candidates) != 1:
        raise UnsupportedNumericDeclarationError("Column must declare exactly one Numeric type")
    return candidates[0]


def _numeric_shape(
    expression: ast.expr,
    *,
    constructors: frozenset[str],
    alias_shapes: dict[str, tuple[int | None, int | None]],
    declaration: str,
) -> tuple[int | None, int | None]:
    constructor_names = constructors | _SQLALCHEMY_NUMERIC_CONSTRUCTORS
    if isinstance(expression, ast.Call):
        called_name = _call_name(expression.func)
        if called_name in alias_shapes and not expression.args and not expression.keywords:
            return alias_shapes[called_name]
        return _numeric_shape_from_call(expression, declaration=declaration)
    referenced_name = _call_name(expression)
    if referenced_name in alias_shapes:
        return alias_shapes[referenced_name]
    if referenced_name in constructor_names:
        return None, None
    raise UnsupportedNumericDeclarationError(
        f"{declaration}: cannot resolve Numeric precision and scale"
    )


def _numeric_column(
    statement: ast.stmt,
    *,
    constructors: frozenset[str],
    numeric_aliases: frozenset[str],
    alias_shapes: dict[str, tuple[int | None, int | None]],
) -> tuple[str, bool, int | None, int | None, str] | None:
    target: ast.Name
    value: ast.expr | None
    if (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ):
        target = statement.targets[0]
        value = statement.value
    elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        target = statement.target
        value = statement.value
    else:
        return None
    if not isinstance(value, ast.Call):
        return None
    numeric_expression = _numeric_type_expression(
        value,
        constructors=constructors,
        numeric_aliases=numeric_aliases,
    )
    if numeric_expression is None:
        return None
    declaration = _call_name(value.func)
    if declaration != "Column":
        raise UnsupportedNumericDeclarationError(
            f"{target.id}: unsupported {declaration or 'unknown'} "
            "Numeric declaration; use Column or extend the guard inventory"
        )
    nullable = True
    for keyword in value.keywords:
        if keyword.arg == "nullable" and isinstance(keyword.value, ast.Constant):
            nullable = bool(keyword.value.value)
    precision, scale = _numeric_shape(
        numeric_expression,
        constructors=constructors,
        alias_shapes=alias_shapes,
        declaration=target.id,
    )
    constructor = (
        _call_name(numeric_expression.func)
        if isinstance(numeric_expression, ast.Call)
        else _call_name(numeric_expression)
    )
    if constructor is None:
        raise UnsupportedNumericDeclarationError(f"{target.id}: cannot resolve Numeric constructor")
    if constructor == "ExactNumeric" and isinstance(numeric_expression, ast.Call):
        for keyword in numeric_expression.keywords:
            if keyword.arg == "decimal_return_scale":
                raise UnsupportedNumericDeclarationError(
                    f"{target.id}: ExactNumeric does not support decimal_return_scale"
                )
            if keyword.arg == "asdecimal" and not (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            ):
                raise UnsupportedNumericDeclarationError(
                    f"{target.id}: ExactNumeric requires asdecimal=True"
                )
    return target.id, nullable, precision, scale, constructor


def inventory_numeric_columns(model_path: Path) -> tuple[NumericColumn, ...]:
    tree = ast.parse(model_path.read_text(encoding="utf-8"), filename=str(model_path))
    constructors = _numeric_constructor_names(tree)
    numeric_aliases = _numeric_type_aliases(tree, constructors=constructors)
    alias_shapes = _numeric_alias_shapes(
        tree,
        constructors=constructors,
        numeric_aliases=numeric_aliases,
    )
    inventory: list[NumericColumn] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        table = _extract_table_name(node)
        if table is None:
            continue
        checks = _extract_check_constraints(node)
        for statement in node.body:
            column = _numeric_column(
                statement,
                constructors=constructors,
                numeric_aliases=numeric_aliases,
                alias_shapes=alias_shapes,
            )
            if column is None:
                continue
            name, nullable, precision, scale, constructor = column
            inventory.append(
                NumericColumn(
                    table=table,
                    column=name,
                    nullable=nullable,
                    precision=precision,
                    scale=scale,
                    constructor=constructor,
                    check_constraints=checks,
                )
            )
    return tuple(inventory)


def _column_pattern(column: str) -> str:
    return rf'(?<![A-Za-z0-9_"])"?{re.escape(column)}"?(?![A-Za-z0-9_"])'


def _finite_operand_pattern(column: str) -> str:
    column_pattern = _column_pattern(column)
    return rf"(?:{column_pattern}|CAST\s*\(\s*{column_pattern}\s+AS\s+TEXT\s*\))"


def _constraint_terms(constraint: str) -> tuple[str, ...]:
    normalized = " ".join(constraint.split())
    return tuple(
        term.strip() for term in re.split(r"\s+\bAND\b\s+", normalized, flags=re.IGNORECASE)
    )


def _is_exact_special_value_list(values: str) -> bool:
    parsed: list[str] = []
    for item in values.split(","):
        match = re.fullmatch(
            r"\s*['\"](?P<value>NaN|Infinity|-Infinity)['\"]"
            r"(?:::(?:numeric|text))?\s*",
            item,
        )
        if match is None:
            return False
        parsed.append(match.group("value"))
    return len(parsed) == 3 and set(parsed) == set(_SPECIAL_NUMERIC_LITERALS)


def _explicitly_excludes_special_values(column: NumericColumn) -> bool:
    finite_operand_pattern = _finite_operand_pattern(column.column)
    for constraint in column.check_constraints:
        terms = _constraint_terms(constraint)
        for term in terms:
            not_in_match = re.fullmatch(
                rf"{finite_operand_pattern}\s+NOT\s+IN\s*\((?P<values>[^)]*)\)",
                term,
                flags=re.IGNORECASE,
            )
            if not_in_match is not None and _is_exact_special_value_list(
                not_in_match.group("values")
            ):
                return True
        if all(
            any(
                re.fullmatch(
                    rf"{finite_operand_pattern}\s*(?:<>|!=)\s*"
                    rf"['\"]{re.escape(value)}['\"](?:::(?:numeric|text))?",
                    term,
                    flags=re.IGNORECASE,
                )
                for term in terms
            )
            for value in _SPECIAL_NUMERIC_LITERALS
        ):
            return True
    return False


def _has_required_sign_constraint(column: NumericColumn, sign: str) -> bool:
    if sign == "signed":
        return True
    operator = r">" if sign == "positive" else r">="
    pattern = rf"{_column_pattern(column.column)}\s*{operator}\s*(?:0(?:\.0*)?)"
    return any(
        re.fullmatch(pattern, term, flags=re.IGNORECASE)
        for check in column.check_constraints
        for term in _constraint_terms(check)
    )


def _contract_entries(contract: dict[str, Any], findings: list[str]) -> dict[str, dict[str, str]]:
    tables = contract.get("tables")
    if not isinstance(tables, dict):
        findings.append("contract.tables must be an object")
        return {}
    entries: dict[str, dict[str, str]] = {}
    for table, columns in tables.items():
        if not isinstance(table, str) or not isinstance(columns, dict):
            findings.append(f"contract table mapping is invalid: {table!r}")
            continue
        if not columns:
            findings.append(f"contract table mapping must not be empty: {table}")
        for column, classification in columns.items():
            identity = f"{table}.{column}"
            if not isinstance(column, str) or not isinstance(classification, dict):
                findings.append(f"{identity}: classification must be an object")
                continue
            if set(classification) != {"profile", "rollout_status"}:
                findings.append(
                    f"{identity}: classification keys must be profile and rollout_status"
                )
                continue
            profile = classification.get("profile")
            rollout_status = classification.get("rollout_status")
            if not isinstance(profile, str) or not isinstance(rollout_status, str):
                findings.append(f"{identity}: classification values must be strings")
                continue
            entries[identity] = {
                "profile": profile,
                "rollout_status": rollout_status,
            }
    return entries


def _storage_shapes(
    contract: dict[str, Any],
    findings: list[str],
) -> dict[str, tuple[int | None, int | None]]:
    payload = contract.get("storage_shapes")
    if not isinstance(payload, dict) or not payload:
        findings.append("contract.storage_shapes must be a non-empty object")
        return {}
    shapes: dict[str, tuple[int | None, int | None]] = {}
    for name, classification in payload.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            findings.append(f"invalid storage-shape name: {name!r}")
            continue
        if not isinstance(classification, dict) or set(classification) != _STORAGE_SHAPE_KEYS:
            findings.append(f"storage shape {name!r} must contain mode, precision, and scale")
            continue
        mode = classification.get("mode")
        precision = classification.get("precision")
        scale = classification.get("scale")
        if mode not in _STORAGE_SHAPE_MODES:
            findings.append(f"storage shape {name!r} has unsupported mode {mode!r}")
            continue
        if mode == "exact-unbounded":
            if precision is not None or scale is not None:
                findings.append(
                    f"storage shape {name!r} exact-unbounded mode requires null precision and scale"
                )
                continue
            shapes[name] = (None, None)
            continue
        if (
            not isinstance(precision, int)
            or isinstance(precision, bool)
            or precision <= 0
            or not isinstance(scale, int)
            or isinstance(scale, bool)
            or scale < 0
            or scale > precision
        ):
            findings.append(
                f"storage shape {name!r} bounded mode requires precision > 0 "
                "and 0 <= scale <= precision"
            )
            continue
        shapes[name] = (precision, scale)
    if len(set(shapes.values())) != len(shapes):
        findings.append("contract.storage_shapes contains duplicate numeric shapes")
    return shapes


def _resolved_storage_shape_names(
    contract: dict[str, Any],
    *,
    identities: set[str],
    shapes: dict[str, tuple[int | None, int | None]],
    findings: list[str],
) -> dict[str, str]:
    default = contract.get("default_storage_shape")
    if not isinstance(default, str) or default not in shapes:
        findings.append("contract.default_storage_shape must name a declared storage shape")
        default = ""
    overrides = contract.get("storage_shape_overrides")
    if not isinstance(overrides, dict):
        findings.append("contract.storage_shape_overrides must be an object")
        overrides = {}
    resolved = {identity: default for identity in identities}
    for identity, shape_name in overrides.items():
        if not isinstance(identity, str) or identity not in identities:
            findings.append(
                f"storage-shape override has no classified Numeric column: {identity!r}"
            )
            continue
        if not isinstance(shape_name, str) or shape_name not in shapes:
            findings.append(
                f"{identity}: storage-shape override names unknown shape {shape_name!r}"
            )
            continue
        if shape_name == default:
            findings.append(f"{identity}: redundant storage-shape override matches the default")
            continue
        resolved[identity] = shape_name
    return resolved


def _table_domain_families(
    contract: dict[str, Any],
    *,
    table_names: set[str],
    findings: list[str],
) -> dict[str, str]:
    families = contract.get("domain_families")
    if not isinstance(families, dict) or not families:
        findings.append("contract.domain_families must be a non-empty object")
        families = {}
    for name, classification in families.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            findings.append(f"invalid domain-family name: {name!r}")
            continue
        if not isinstance(classification, dict) or set(classification) != _DOMAIN_FAMILY_KEYS:
            findings.append(f"domain family {name!r} must contain owner and boundary_class")
            continue
        owner = classification.get("owner")
        boundary_class = classification.get("boundary_class")
        if not isinstance(owner, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", owner):
            findings.append(f"domain family {name!r} has invalid owner {owner!r}")
        if boundary_class not in _BOUNDARY_CLASSES:
            findings.append(
                f"domain family {name!r} has unsupported boundary_class {boundary_class!r}"
            )

    mappings = contract.get("table_domain_families")
    if not isinstance(mappings, dict):
        findings.append("contract.table_domain_families must be an object")
        mappings = {}
    mapping_names = {name for name in mappings if isinstance(name, str)}
    for table in sorted(table_names - mapping_names):
        findings.append(f"{table}: Numeric table is missing a domain-family owner")
    for table in sorted(mapping_names - table_names):
        findings.append(f"{table}: domain-family mapping has no classified Numeric table")
    resolved: dict[str, str] = {}
    for table, family in mappings.items():
        if not isinstance(table, str) or table not in table_names:
            continue
        if not isinstance(family, str) or family not in families:
            findings.append(f"{table}: domain-family mapping names unknown family {family!r}")
            continue
        resolved[table] = family
    for family in sorted(set(families) - set(resolved.values())):
        findings.append(f"domain family {family!r} is not assigned to a Numeric table")
    return resolved


def evaluate_guard(repo_root: Path = ROOT, contract_path: Path | None = None) -> GuardReport:
    findings: list[str] = []
    path = contract_path or repo_root / DEFAULT_CONTRACT_PATH
    try:
        contract = _load_contract(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return GuardReport(
            findings=(f"cannot load contract {path}: {exc}",),
            numeric_column_count=0,
            table_count=0,
            bounded_numeric_count=0,
            unbounded_numeric_count=0,
            domain_family_count=0,
            orm_enforced_count=0,
            database_enforced_count=0,
            planned_count=0,
        )

    if contract.get("schema_version") != "2.0.0":
        findings.append("contract.schema_version must be 2.0.0")
    if set(contract) != _V2_CONTRACT_KEYS:
        findings.append(
            "contract v2 keys must be schema_version, model_path, expected_inventory, "
            "profiles, rollout_statuses, storage_shapes, default_storage_shape, "
            "exact_bind_enforcement, storage_shape_overrides, domain_families, "
            "table_domain_families, and tables"
        )
    if contract.get("exact_bind_enforcement") != "required":
        findings.append("contract.exact_bind_enforcement must be required")
    if contract.get("profiles") != _CANONICAL_PROFILES:
        findings.append("contract.profiles must match the canonical finite-policy vocabulary")
    statuses = contract.get("rollout_statuses")
    if not isinstance(statuses, list) or set(statuses) != _ROLLOUT_STATUSES:
        findings.append(
            "contract.rollout_statuses must contain orm-enforced and planned exactly once"
        )
    elif len(statuses) != len(_ROLLOUT_STATUSES):
        findings.append("contract.rollout_statuses contains duplicate values")

    model_relative = contract.get("model_path")
    if not isinstance(model_relative, str) or Path(model_relative).is_absolute():
        findings.append("contract.model_path must be a repository-relative string")
        inventory: tuple[NumericColumn, ...] = ()
    else:
        try:
            inventory = inventory_numeric_columns(repo_root / model_relative)
        except (OSError, SyntaxError, UnsupportedNumericDeclarationError) as exc:
            findings.append(f"cannot inventory ORM model {model_relative}: {exc}")
            inventory = ()

    model_entries = {column.identity: column for column in inventory}
    if len(model_entries) != len(inventory):
        findings.append("ORM inventory contains duplicate table.column identities")
    contract_entries = _contract_entries(contract, findings)
    shapes = _storage_shapes(contract, findings)
    resolved_shape_names = _resolved_storage_shape_names(
        contract,
        identities=set(contract_entries),
        shapes=shapes,
        findings=findings,
    )
    resolved_domain_families = _table_domain_families(
        contract,
        table_names={identity.split(".", maxsplit=1)[0] for identity in contract_entries},
        findings=findings,
    )

    expected = contract.get("expected_inventory")
    if not isinstance(expected, dict) or set(expected) != {"numeric_columns", "tables"}:
        findings.append("contract.expected_inventory must contain numeric_columns and tables")
    else:
        if expected.get("numeric_columns") != len(inventory):
            findings.append(
                "contract.expected_inventory.numeric_columns "
                f"is {expected.get('numeric_columns')!r}; ORM has {len(inventory)}"
            )
        table_count = len({column.table for column in inventory})
        if expected.get("tables") != table_count:
            findings.append(
                f"contract.expected_inventory.tables is {expected.get('tables')!r}; "
                f"ORM has {table_count}"
            )

    for identity in sorted(set(model_entries) - set(contract_entries)):
        findings.append(f"{identity}: Numeric column is missing a classification")
    for identity in sorted(set(contract_entries) - set(model_entries)):
        findings.append(f"{identity}: classification has no matching ORM Numeric column")

    orm_enforced_count = 0
    planned_count = 0
    for identity in sorted(set(model_entries) & set(contract_entries)):
        column = model_entries[identity]
        classification = contract_entries[identity]
        profile_name = classification["profile"]
        rollout_status = classification["rollout_status"]
        profile = _CANONICAL_PROFILES.get(profile_name)
        if rollout_status not in _ROLLOUT_STATUSES:
            findings.append(f"{identity}: unknown rollout_status {rollout_status!r}")
        if profile is None:
            findings.append(f"{identity}: unknown finite-policy profile {profile_name!r}")
            continue
        if rollout_status not in _ROLLOUT_STATUSES:
            continue
        if column.nullable != profile["nullable"]:
            findings.append(
                f"{identity}: ORM nullable={column.nullable} conflicts with {profile_name}"
            )
        shape_name = resolved_shape_names.get(identity)
        expected_shape = shapes.get(shape_name) if shape_name is not None else None
        actual_shape = (column.precision, column.scale)
        if expected_shape is not None and actual_shape != expected_shape:
            findings.append(
                f"{identity}: ORM Numeric{actual_shape!r} conflicts with "
                f"storage shape {shape_name!r} Numeric{expected_shape!r}"
            )
        if (
            contract.get("exact_bind_enforcement") == "required"
            and column.constructor != "ExactNumeric"
        ):
            findings.append(
                f"{identity}: precision contract requires ExactNumeric bind enforcement; "
                f"found {column.constructor}"
            )
        finite_enforced = _explicitly_excludes_special_values(column)
        sign_enforced = _has_required_sign_constraint(column, str(profile["sign"]))
        if rollout_status == "orm-enforced":
            orm_enforced_count += 1
            if not finite_enforced:
                findings.append(
                    f"{identity}: {rollout_status} classification lacks an explicit "
                    "ORM exclusion of NaN, Infinity, and -Infinity"
                )
            if not sign_enforced:
                findings.append(
                    f"{identity}: {rollout_status} classification lacks the "
                    f"{profile['sign']} ORM sign check"
                )
        else:
            planned_count += 1
            if finite_enforced and sign_enforced:
                findings.append(
                    f"{identity}: ORM enforces {profile_name} but rollout_status is still planned"
                )

    return GuardReport(
        findings=tuple(findings),
        numeric_column_count=len(inventory),
        table_count=len({column.table for column in inventory}),
        bounded_numeric_count=sum(not column.is_unbounded for column in inventory),
        unbounded_numeric_count=sum(column.is_unbounded for column in inventory),
        domain_family_count=len(set(resolved_domain_families.values())),
        orm_enforced_count=orm_enforced_count,
        database_enforced_count=0,
        planned_count=planned_count,
    )


def main() -> int:
    report = evaluate_guard()
    if report.findings:
        print("Financial numeric persistence guard failed:")
        for finding in report.findings:
            print(f"- {finding}")
        return 1
    print(
        "Financial numeric persistence guard passed: "
        f"{report.numeric_column_count} Numeric columns across {report.table_count} tables; "
        f"{report.bounded_numeric_count} bounded, "
        f"{report.unbounded_numeric_count} unbounded; "
        f"{report.domain_family_count} domain families; "
        f"{report.orm_enforced_count} ORM-enforced, "
        f"{report.database_enforced_count} database-enforced, "
        f"{report.planned_count} planned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
