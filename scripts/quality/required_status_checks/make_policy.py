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
_EXECUTION_SPECIAL_TARGET = re.compile(
    r"^(?:"
    + "|".join(re.escape(target) for target in sorted(_EXECUTION_SPECIAL_TARGETS))
    + r")\s*:"
)
_VPATH_DIRECTIVE = re.compile(r"^vpath(?:\s|$)")


def validate_make_execution_state(line: str, *, path: Path, line_number: int) -> None:
    """Reject Make syntax that can alter parsing or execution of governed targets."""

    mutable_state = any(
        pattern.match(line)
        for pattern in (
            _EXECUTION_ASSIGNMENT,
            _EXECUTION_SPECIAL_TARGET,
            _VPATH_DIRECTIVE,
        )
    )
    if mutable_state:
        raise RequiredStatusChecksError(
            f"Makefile execution state must be static: {path}; line={line_number}"
        )
