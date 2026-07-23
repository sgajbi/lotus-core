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
_ROLLOUT_STATUSES = {"enforced", "planned"}
_SPECIAL_NUMERIC_LITERALS = ("NaN", "Infinity", "-Infinity")


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
    enforced_count: int
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


def _numeric_column(statement: ast.stmt) -> tuple[str, bool] | None:
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
        isinstance(argument, ast.Call) and _call_name(argument.func) == "Numeric"
        for argument in value.args
    )
    keyword_numeric = any(
        keyword.arg == "type_"
        and isinstance(keyword.value, ast.Call)
        and _call_name(keyword.value.func) == "Numeric"
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
    inventory: list[NumericColumn] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        table = _extract_table_name(node)
        if table is None:
            continue
        checks = _extract_check_constraints(node)
        for statement in node.body:
            column = _numeric_column(statement)
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
            enforced_count=0,
            planned_count=0,
        )

    if contract.get("schema_version") != "1.0.0":
        findings.append("contract.schema_version must be 1.0.0")
    if contract.get("profiles") != _CANONICAL_PROFILES:
        findings.append("contract.profiles must match the canonical finite-policy vocabulary")
    statuses = contract.get("rollout_statuses")
    if not isinstance(statuses, list) or set(statuses) != _ROLLOUT_STATUSES:
        findings.append("contract.rollout_statuses must contain enforced and planned exactly once")
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

    enforced_count = 0
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
        if rollout_status == "enforced":
            enforced_count += 1
            if not finite_enforced:
                findings.append(
                    f"{identity}: enforced classification lacks an explicit exclusion of "
                    "NaN, Infinity, and -Infinity"
                )
            if not sign_enforced:
                findings.append(
                    f"{identity}: enforced classification lacks the {profile['sign']} sign check"
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
        enforced_count=enforced_count,
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
        f"{report.enforced_count} enforced, {report.planned_count} planned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
