from __future__ import annotations

import re
from pathlib import Path

from scripts.quality.required_status_checks.model import RequiredStatusChecksError

_EXECUTION_VARIABLES = frozenset(
    {
        ".RECIPEPREFIX",
        ".SHELLFLAGS",
        "GNUMAKEFLAGS",
        "MAKE",
        "MAKEFILES",
        "MAKEFLAGS",
        "SHELL",
        "VPATH",
    }
)
_EXECUTION_SPECIAL_TARGETS = frozenset(
    {
        ".DEFAULT",
        ".EXPORT_ALL_VARIABLES",
        ".IGNORE",
        ".ONESHELL",
        ".POSIX",
        ".SILENT",
    }
)
_EXECUTION_ASSIGNMENT = re.compile(
    r"^(?:[^:=]+:{1,2}\s*)?(?:(?:export|override|private)\s+)*(?:"
    + "|".join(re.escape(variable) for variable in sorted(_EXECUTION_VARIABLES))
    + r")\s*(?:::=|:=|\+=|\?=|!=|=)"
)
_EXECUTION_DEFINE = re.compile(
    r"^(?:(?:export|override|private)\s+)*define\s+(?:"
    + "|".join(re.escape(variable) for variable in sorted(_EXECUTION_VARIABLES))
    + r")(?=\s|$|::=|:=|\+=|\?=|!=|=)"
)
_VPATH_DIRECTIVE = re.compile(r"^vpath(?:\s|$)")
_AUTHORITY_FUNCTION = re.compile(r"\$(?:\(|\{)\s*(?:call|eval)(?=[\s,)}])")
_SAFE_DIAGNOSTIC_EXPANSION = re.compile(r"^\$\((?:error|info|warning)(?:\s|$).*\)$")
_ASSIGNMENT_OPERATORS = ("::=", ":=", "+=", "?=", "!=", "=")


def _first_unexpanded_token(line: str, tokens: tuple[str, ...]) -> int | None:
    expression_closers: list[str] = []
    index = 0
    while index < len(line):
        if line.startswith("$(", index):
            expression_closers.append(")")
            index += 2
            continue
        if line.startswith("${", index):
            expression_closers.append("}")
            index += 2
            continue
        if expression_closers:
            if line[index] == expression_closers[-1]:
                expression_closers.pop()
            index += 1
            continue
        if any(line.startswith(token, index) for token in tokens):
            return index
        index += 1
    return None


def _has_expansion_dependent_declaration(line: str) -> bool:
    """Reject declarations whose structure depends on expanding a Make variable."""

    boundaries = (
        boundary
        for boundary in (
            _first_unexpanded_token(line, ("#",)),
            _first_unexpanded_token(line, (";",)),
        )
        if boundary is not None
    )
    declaration = line[: min(boundaries, default=len(line))].strip()
    if "$" not in declaration or _SAFE_DIAGNOSTIC_EXPANSION.fullmatch(declaration):
        return False
    assignment = _first_unexpanded_token(declaration, _ASSIGNMENT_OPERATORS)
    if assignment is not None:
        return "$" in declaration[:assignment]
    target_separator = _first_unexpanded_token(declaration, (":",))
    if target_separator is not None:
        return "$" in declaration[:target_separator]
    return True


def _has_execution_special_target(line: str) -> bool:
    target_separator = _first_unexpanded_token(line, (":",))
    assignment = _first_unexpanded_token(line, _ASSIGNMENT_OPERATORS)
    if target_separator is None or (assignment is not None and target_separator >= assignment):
        return False
    return bool(set(line[:target_separator].split()) & _EXECUTION_SPECIAL_TARGETS)


def validate_make_authority_functions(lines: list[str], *, path: Path) -> None:
    """Reject authority functions after joining Make logical-line continuations."""

    logical_line: str | None = None
    logical_line_number = 0
    for line_number, raw_line in enumerate(lines, start=1):
        if logical_line is None:
            logical_line = raw_line
            logical_line_number = line_number
        else:
            continuation = raw_line[1:] if raw_line.startswith("\t") else raw_line
            logical_line += f" {continuation}"
        if logical_line.endswith("\\"):
            logical_line = logical_line[:-1]
            continue
        if _AUTHORITY_FUNCTION.search(logical_line):
            raise RequiredStatusChecksError(
                f"Makefile phony authority must be static: {path}; line={logical_line_number}"
            )
        logical_line = None


def validate_make_execution_state(line: str, *, path: Path, line_number: int) -> None:
    """Reject Make syntax that can alter parsing or execution of governed targets."""

    mutable_state = (
        (line.endswith("\\") and not line.startswith(".PHONY:"))
        or _has_expansion_dependent_declaration(line)
        or _has_execution_special_target(line)
        or any(
            pattern.match(line)
            for pattern in (
                _EXECUTION_ASSIGNMENT,
                _EXECUTION_DEFINE,
                _VPATH_DIRECTIVE,
            )
        )
    )
    if mutable_state:
        raise RequiredStatusChecksError(
            f"Makefile execution state must be static: {path}; line={line_number}"
        )
