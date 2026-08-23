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
_EXECUTION_SPECIAL_TARGET = re.compile(
    r"^(?:"
    + "|".join(re.escape(target) for target in sorted(_EXECUTION_SPECIAL_TARGETS))
    + r")\s*:"
)
_VPATH_DIRECTIVE = re.compile(r"^vpath(?:\s|$)")
_DEFINE_DIRECTIVE = re.compile(r"^(?:(?:export|override|private)\s+)*define\s+(\S+)")
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


def _has_computed_declaration_name(line: str) -> bool:
    assignment = _first_unexpanded_token(line, _ASSIGNMENT_OPERATORS)
    if assignment is not None and "$" in line[:assignment]:
        return True
    target_separator = _first_unexpanded_token(line, (":",))
    if (
        target_separator is not None
        and (assignment is None or target_separator < assignment)
        and "$" in line[:target_separator]
    ):
        return True
    define = _DEFINE_DIRECTIVE.match(line)
    return define is not None and "$" in define.group(1)


def validate_make_execution_state(line: str, *, path: Path, line_number: int) -> None:
    """Reject Make syntax that can alter parsing or execution of governed targets."""

    mutable_state = _has_computed_declaration_name(line) or any(
        pattern.match(line)
        for pattern in (
            _EXECUTION_ASSIGNMENT,
            _EXECUTION_DEFINE,
            _EXECUTION_SPECIAL_TARGET,
            _VPATH_DIRECTIVE,
        )
    )
    if mutable_state:
        raise RequiredStatusChecksError(
            f"Makefile execution state must be static: {path}; line={line_number}"
        )
