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
_ROLLOUT_STATUSES = {"orm-enforced", "database-enforced", "planned"}
_ORM_ENFORCED_STATUSES = {"orm-enforced", "database-enforced"}
_SPECIAL_NUMERIC_LITERALS = ("NaN", "Infinity", "-Infinity")
_SQLALCHEMY_NUMERIC_CONSTRUCTORS = {"Numeric", "NUMERIC", "DECIMAL"}


class DuplicateContractKeyError(ValueError):
    pass


class UnsupportedNumericDeclarationError(ValueError):
    pass


@dataclass(frozen=True)
class NumericColumn:
    table: str
    column: str
    nullable: bool
    check_constraints: tuple[str, ...]

    @property
    def identity(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass(frozen=True)
class GuardReport:
    findings: tuple[str, ...]
    numeric_column_count: int
    table_count: int
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
        if not isinstance(node, ast.Call) or _call_name(node.func) != "CheckConstraint":
            continue
        if not node.args:
            continue
        expression = _constant_string(node.args[0])
        if expression is not None:
            checks.append(expression)
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
        isinstance(expression, ast.Call) and _call_name(expression.func) in constructor_names
    ) or (
        isinstance(expression, ast.Name)
        and (expression.id in constructor_names or expression.id in numeric_aliases)
    )


def _numeric_column(
    statement: ast.stmt,
    *,
    constructors: frozenset[str],
    numeric_aliases: frozenset[str],
) -> tuple[str, bool] | None:
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
    positional_numeric = any(
        _is_numeric_type(
            argument,
            constructors=constructors,
            numeric_aliases=numeric_aliases,
        )
        for argument in value.args
    )
    keyword_numeric = any(
        keyword.arg == "type_"
        and _is_numeric_type(
            keyword.value,
            constructors=constructors,
            numeric_aliases=numeric_aliases,
        )
        for keyword in value.keywords
    )
    if not positional_numeric and not keyword_numeric:
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
    return target.id, nullable


def inventory_numeric_columns(model_path: Path) -> tuple[NumericColumn, ...]:
    tree = ast.parse(model_path.read_text(encoding="utf-8"), filename=str(model_path))
    constructors = _numeric_constructor_names(tree)
    numeric_aliases = _numeric_type_aliases(tree, constructors=constructors)
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
            )
            if column is None:
                continue
            name, nullable = column
            inventory.append(
                NumericColumn(
                    table=table,
                    column=name,
                    nullable=nullable,
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


def _evidence_path(
    *,
    repo_root: Path,
    raw_path: object,
    identity: str,
    field_name: str,
    findings: list[str],
) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        findings.append(f"{identity}: {field_name} must be a nonempty repository-relative path")
        return None
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        findings.append(f"{identity}: {field_name} must stay within the repository")
        return None
    resolved = (repo_root / relative).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        findings.append(f"{identity}: {field_name} must stay within the repository")
        return None
    if not resolved.is_file():
        findings.append(f"{identity}: {field_name} does not exist: {raw_path}")
        return None
    return resolved


def _validate_database_enforcement_evidence(
    *,
    contract: dict[str, Any],
    contract_entries: dict[str, dict[str, str]],
    repo_root: Path,
    findings: list[str],
) -> None:
    evidence = contract.get("database_enforcement_evidence")
    if not isinstance(evidence, dict):
        findings.append("contract.database_enforcement_evidence must be an object")
        return
    database_identities = {
        identity
        for identity, classification in contract_entries.items()
        if classification["rollout_status"] == "database-enforced"
    }
    for identity in sorted(database_identities - set(evidence)):
        findings.append(f"{identity}: database-enforced classification lacks database evidence")
    for identity in sorted(set(evidence) - database_identities):
        findings.append(
            f"{identity}: database evidence has no matching database-enforced classification"
        )
    for identity in sorted(database_identities & set(evidence)):
        item = evidence[identity]
        if not isinstance(item, dict) or set(item) != {
            "migration_path",
            "constraint_names",
            "postgresql_test_paths",
        }:
            findings.append(
                f"{identity}: database evidence must contain migration_path, "
                "constraint_names, and postgresql_test_paths"
            )
            continue
        migration_path = item["migration_path"]
        migration = _evidence_path(
            repo_root=repo_root,
            raw_path=migration_path,
            identity=identity,
            field_name="migration_path",
            findings=findings,
        )
        if isinstance(migration_path, str) and (
            not Path(migration_path).as_posix().startswith("alembic/versions/")
            or Path(migration_path).suffix != ".py"
        ):
            findings.append(
                f"{identity}: migration_path must be a Python migration under alembic/versions"
            )
        constraint_names = item["constraint_names"]
        valid_constraint_names = (
            isinstance(constraint_names, list)
            and bool(constraint_names)
            and all(isinstance(name, str) for name in constraint_names)
            and len(constraint_names) == len(set(constraint_names))
            and all(re.fullmatch(r"[a-z][a-z0-9_]+", name) is not None for name in constraint_names)
        )
        if not valid_constraint_names:
            findings.append(f"{identity}: constraint_names must be unique nonempty SQL identifiers")
            declared_constraint_names: list[str] = []
        elif migration is not None:
            declared_constraint_names = constraint_names
            migration_source = migration.read_text(encoding="utf-8")
            for name in constraint_names:
                if re.search(rf"['\"]{re.escape(name)}['\"]", migration_source) is None:
                    findings.append(f"{identity}: migration does not contain constraint {name}")
        else:
            declared_constraint_names = constraint_names
        test_paths = item["postgresql_test_paths"]
        if (
            not isinstance(test_paths, list)
            or not test_paths
            or not all(isinstance(test_path, str) for test_path in test_paths)
            or len(test_paths) != len(set(test_paths))
        ):
            findings.append(
                f"{identity}: postgresql_test_paths must be a nonempty unique path list"
            )
            continue
        for index, test_path in enumerate(test_paths):
            resolved_test = _evidence_path(
                repo_root=repo_root,
                raw_path=test_path,
                identity=identity,
                field_name=f"postgresql_test_paths[{index}]",
                findings=findings,
            )
            if isinstance(test_path, str) and not Path(test_path).as_posix().startswith(
                "tests/integration/"
            ):
                findings.append(
                    f"{identity}: PostgreSQL evidence path must be under tests/integration: "
                    f"{test_path}"
                )
            if resolved_test is not None and (
                resolved_test.suffix != ".py" or not resolved_test.name.startswith("test_")
            ):
                findings.append(
                    f"{identity}: PostgreSQL evidence path must be a Python test: {test_path}"
                )
            if resolved_test is not None:
                test_source = resolved_test.read_text(encoding="utf-8")
                if identity not in test_source and not any(
                    name in test_source for name in declared_constraint_names
                ):
                    findings.append(
                        f"{identity}: PostgreSQL test does not reference the identity "
                        "or a declared constraint"
                    )


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
            orm_enforced_count=0,
            database_enforced_count=0,
            planned_count=0,
        )

    if contract.get("schema_version") != "1.0.0":
        findings.append("contract.schema_version must be 1.0.0")
    if contract.get("profiles") != _CANONICAL_PROFILES:
        findings.append("contract.profiles must match the canonical finite-policy vocabulary")
    statuses = contract.get("rollout_statuses")
    if not isinstance(statuses, list) or set(statuses) != _ROLLOUT_STATUSES:
        findings.append(
            "contract.rollout_statuses must contain orm-enforced, database-enforced, "
            "and planned exactly once"
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
    _validate_database_enforcement_evidence(
        contract=contract,
        contract_entries=contract_entries,
        repo_root=repo_root,
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
    database_enforced_count = 0
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
        finite_enforced = _explicitly_excludes_special_values(column)
        sign_enforced = _has_required_sign_constraint(column, str(profile["sign"]))
        if rollout_status in _ORM_ENFORCED_STATUSES:
            if rollout_status == "orm-enforced":
                orm_enforced_count += 1
            else:
                database_enforced_count += 1
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
        orm_enforced_count=orm_enforced_count,
        database_enforced_count=database_enforced_count,
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
        f"{report.orm_enforced_count} ORM-enforced, "
        f"{report.database_enforced_count} database-enforced, "
        f"{report.planned_count} planned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
