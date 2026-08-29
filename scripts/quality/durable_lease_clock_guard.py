"""Reject application-clock values used to mint durable lease deadlines."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEADLINE_SUFFIX = "_expires_at"
_APPLICATION_CLOCK_CALLS = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("datetime", "today"),
    ("timezone", "now"),
}
_APPLICATION_CLOCK_HELPER_NAMES = {
    "utc_now",
    "now_utc",
    "utcnow",
    "today",
    "current_time",
    "current_timestamp",
    "application_deadline",
}
_TRANSACTION_START_SQL_CLOCKS = {
    "current_date",
    "current_timestamp",
    "localtimestamp",
    "now",
    "transaction_timestamp",
}


@dataclass(frozen=True, slots=True)
class DurableLeaseClockFinding:
    file: str
    line: int
    column: int
    target: str


def _attribute_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return tuple(reversed(parts))


def _contains_application_clock(
    node: ast.AST,
    application_clock_names: set[str] | None = None,
    application_clock_calls: set[tuple[str, str]] | None = None,
) -> bool:
    application_clock_names = application_clock_names or set()
    application_clock_calls = application_clock_calls or _APPLICATION_CLOCK_CALLS
    if isinstance(node, ast.Name):
        return node.id in application_clock_names
    if isinstance(node, ast.BinOp):
        return _contains_application_clock(
            node.left,
            application_clock_names,
            application_clock_calls,
        ) or _contains_application_clock(
            node.right,
            application_clock_names,
            application_clock_calls,
        )
    if isinstance(node, ast.UnaryOp):
        return _contains_application_clock(
            node.operand,
            application_clock_names,
            application_clock_calls,
        )
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            chain = _attribute_chain(child.func)
            if len(chain) >= 2 and tuple(chain[-2:]) in application_clock_calls:
                return True
            if (
                len(chain) >= 2
                and chain[-2] == "func"
                and chain[-1] in _TRANSACTION_START_SQL_CLOCKS
            ):
                return True
            if chain and (
                chain[-1] in _APPLICATION_CLOCK_HELPER_NAMES
                or chain[-1].endswith("_now")
                or "deadline" in chain[-1].lower()
            ):
                return True
    return False


def _application_clock_calls(tree: ast.AST) -> set[tuple[str, str]]:
    calls = set(_APPLICATION_CLOCK_CALLS)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "datetime":
            continue
        for imported in node.names:
            if imported.name == "datetime":
                alias = imported.asname or imported.name
                calls.update((alias, method) for method in ("now", "utcnow", "today"))
            elif imported.name == "timezone":
                alias = imported.asname or imported.name
                calls.add((alias, "now"))
    return calls


def _walk_lexical_scope(scope: ast.AST):
    """Yield nodes in one lexical scope without traversing nested scopes."""

    stack = [scope]
    while stack:
        node = stack.pop()
        yield node
        for child in reversed(list(ast.iter_child_nodes(node))):
            if node is not scope and isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                yield child
                continue
            stack.append(child)


def _assignment_pairs(tree: ast.AST) -> list[tuple[list[str], ast.AST]]:
    pairs: list[tuple[list[str], ast.AST]] = []
    for node in _walk_lexical_scope(tree):
        if isinstance(node, ast.Assign):
            pairs.extend((_target_names(target), node.value) for target in node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            pairs.append((_target_names(node.target), node.value))
    return pairs


def _application_clock_names(
    tree: ast.AST,
    application_clock_calls: set[tuple[str, str]],
    initial_names: set[str] | None = None,
) -> set[str]:
    """Conservatively taint locals derived from application-clock expressions."""

    names: set[str] = set(initial_names or ())
    pairs = _assignment_pairs(tree)
    changed = True
    while changed:
        changed = False
        for targets, value in pairs:
            if _contains_application_clock(value, names, application_clock_calls):
                before = len(names)
                names.update(targets)
                changed = changed or len(names) != before
    return names


def _expanded_deadline_targets(
    tree: ast.AST,
    application_clock_names: set[str],
    application_clock_calls: set[tuple[str, str]],
) -> dict[str, set[str]]:
    """Find deadline keys hidden behind ``**mapping`` call expansions."""

    mappings: dict[str, set[str]] = {}
    for node in _walk_lexical_scope(tree):
        if isinstance(node, ast.Assign):
            assignments = [(_target_names(target), node.value) for target in node.targets]
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            assignments = [(_target_names(node.target), node.value)]
        else:
            continue
        for targets, value in assignments:
            deadline_targets: set[str] = set()
            if isinstance(value, ast.Dict):
                for key, item_value in zip(value.keys, value.values, strict=False):
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value.endswith(_DEADLINE_SUFFIX)
                        and _contains_application_clock(
                            item_value,
                            application_clock_names,
                            application_clock_calls,
                        )
                    ):
                        deadline_targets.add(key.value)
            elif isinstance(value, ast.Name):
                deadline_targets.update(mappings.get(value.id, set()))
            for target in targets:
                if deadline_targets:
                    mappings.setdefault(target, set()).update(deadline_targets)
    return mappings


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in node.elts:
            names.extend(_target_names(element))
        return names
    return []


def find_durable_lease_clock_findings(
    *,
    repo_root: Path = REPO_ROOT,
    source_root: Path | None = None,
) -> list[DurableLeaseClockFinding]:
    root = source_root or repo_root / "src"
    findings: list[DurableLeaseClockFinding] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        application_clock_calls = _application_clock_calls(tree)
        module_names = _application_clock_names(tree, application_clock_calls)
        scopes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        scopes.insert(0, tree)
        for scope in scopes:
            application_clock_names = _application_clock_names(
                scope,
                application_clock_calls,
                initial_names=module_names if scope is not tree else None,
            )
            expanded_deadline_targets = _expanded_deadline_targets(
                scope,
                application_clock_names,
                application_clock_calls,
            )
            for node in _walk_lexical_scope(scope):
                assignments: list[tuple[list[str], ast.AST]] = []
                if isinstance(node, ast.Assign):
                    assignments = [(_target_names(target), node.value) for target in node.targets]
                elif isinstance(node, ast.AnnAssign):
                    assignments = [(_target_names(node.target), node.value)] if node.value else []
                elif isinstance(node, ast.Call):
                    assignments = [
                        ([keyword.arg], keyword.value)
                        for keyword in node.keywords
                        if keyword.arg and keyword.arg.endswith(_DEADLINE_SUFFIX)
                    ]
                    for keyword in node.keywords:
                        if keyword.arg is None and isinstance(keyword.value, ast.Name):
                            assignments.append(
                                (
                                    list(expanded_deadline_targets.get(keyword.value.id, set())),
                                    keyword.value,
                                )
                            )
                        elif keyword.arg is None and isinstance(keyword.value, ast.Dict):
                            assignments.extend(
                                ([key.value], item_value)
                                for key, item_value in zip(
                                    keyword.value.keys,
                                    keyword.value.values,
                                    strict=False,
                                )
                                if isinstance(key, ast.Constant)
                                and isinstance(key.value, str)
                                and key.value.endswith(_DEADLINE_SUFFIX)
                            )
                    for argument in node.args:
                        if isinstance(argument, ast.Name):
                            assignments.extend(
                                (
                                    [target],
                                    argument,
                                )
                                for target in expanded_deadline_targets.get(argument.id, set())
                            )
                        elif isinstance(argument, ast.Dict):
                            assignments.extend(
                                ([key.value], item_value)
                                for key, item_value in zip(
                                    argument.keys,
                                    argument.values,
                                    strict=False,
                                )
                                if isinstance(key, ast.Constant)
                                and isinstance(key.value, str)
                                and key.value.endswith(_DEADLINE_SUFFIX)
                            )
                for targets, value in assignments:
                    for target in targets:
                        if target.endswith(_DEADLINE_SUFFIX) and _contains_application_clock(
                            value,
                            application_clock_names,
                            application_clock_calls,
                        ):
                            findings.append(
                                DurableLeaseClockFinding(
                                    file=path.relative_to(repo_root).as_posix(),
                                    line=node.lineno,
                                    column=node.col_offset,
                                    target=target,
                                )
                            )
    return findings


def main() -> int:
    findings = find_durable_lease_clock_findings()
    if findings:
        print("Durable lease clock guard failed:")
        for finding in findings:
            print(f"{finding.file}:{finding.line}:{finding.column}: {finding.target}")
        return 1
    print("Durable lease clock guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
