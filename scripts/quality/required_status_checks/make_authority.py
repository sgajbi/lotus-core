from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from scripts.quality.required_status_checks.make_policy import (
    recursive_make_recipe_targets,
    static_recipe_command_variables,
    validate_governed_recipe_commands,
    validate_make_authority_functions,
    validate_make_execution_state,
    validate_make_recipe_failure_propagation,
)
from scripts.quality.required_status_checks.model import RequiredStatusChecksError

_MAKE_TARGET_RECORD = re.compile(r"^([^\s#][^\s:]*):")
_PHONY_TARGET_FLAG = "#  Phony target (prerequisite of .PHONY)."
_MAKE_DATABASE_COMMAND = (
    "make",
    "--no-builtin-rules",
    "--no-builtin-variables",
    "--question",
    "--print-data-base",
)
_MAKE_DATABASE_START = "# Make data base, printed on "
_MAKE_DATABASE_END = "# Finished Make data base on "
_MAKE_DATABASE_FILES = "# Files"
_MAKE_CONDITIONAL_DIRECTIVE = re.compile(r"^(?:ifeq|ifneq|ifdef|ifndef|else|endif)(?:\s|$)")
_MAKE_DEFINE_DIRECTIVE = re.compile(r"^(?:(?:export|override|private)\s+)*define(?:\s|$)")
_MAKE_ENDEF_DIRECTIVE = re.compile(r"^endef(?:\s|$)")
_MAKE_INCLUDE_DIRECTIVE = re.compile(r"^(?:-?include|sinclude)(?:\s|$)")
_STATIC_PHONY_DECLARATION = re.compile(r"^\.PHONY:\s*(.*?)\s*$")
_STATIC_PHONY_TARGET = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class MakeTargetAuthority:
    prerequisites: tuple[str, ...]
    recipes: tuple[str, ...]
    phony: bool


def _make_database_files_lines(output_lines: list[str], *, path: Path) -> list[str]:
    database_starts = [
        index for index, line in enumerate(output_lines) if line.startswith(_MAKE_DATABASE_START)
    ]
    database_ends = [
        index for index, line in enumerate(output_lines) if line.startswith(_MAKE_DATABASE_END)
    ]
    if not database_starts or not database_ends or database_ends[-1] <= database_starts[-1]:
        raise RequiredStatusChecksError(f"unable to parse Makefile effective database: {path}")
    files_sections = [
        index
        for index, line in enumerate(output_lines)
        if line == _MAKE_DATABASE_FILES and database_starts[-1] < index < database_ends[-1]
    ]
    if not files_sections:
        raise RequiredStatusChecksError(f"Makefile effective database has no Files section: {path}")
    return output_lines[files_sections[-1] + 1 : database_ends[-1]]


def _make_target_authority_from_files_section(
    lines: list[str],
    *,
    path: Path,
) -> dict[str, MakeTargetAuthority]:
    targets: dict[str, MakeTargetAuthority] = {}
    current_target: str | None = None
    prerequisites: tuple[str, ...] = ()
    recipes: list[str] = []
    phony = False

    def store_current_target() -> None:
        if current_target is not None:
            if current_target in targets:
                raise RequiredStatusChecksError(
                    f"Makefile effective database contains repeated target authority: "
                    f"{path}; target={current_target}"
                )
            targets[current_target] = MakeTargetAuthority(
                prerequisites=prerequisites,
                recipes=tuple(recipes),
                phony=phony,
            )

    for line in lines:
        record = _MAKE_TARGET_RECORD.match(line)
        if record is not None:
            store_current_target()
            current_target = record.group(1)
            prerequisites = tuple(
                token
                for token in line[record.end() :].split()
                if _STATIC_PHONY_TARGET.fullmatch(token) is not None
            )
            recipes = []
            phony = False
            continue
        if line == _PHONY_TARGET_FLAG and current_target is not None:
            phony = True
            continue
        if line.startswith("\t") and current_target is not None:
            recipes.append(line[1:])
            continue
        if not line or not line.startswith("#"):
            store_current_target()
            current_target = None
    store_current_target()
    return targets


def _static_phony_targets(path: Path) -> frozenset[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RequiredStatusChecksError(f"unable to load Makefile phony targets: {path}") from exc
    validate_make_authority_functions(lines, path=path)
    static_command_variables = static_recipe_command_variables(lines)
    targets: set[str] = set()
    define_depth = 0
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        validate_make_recipe_failure_propagation(
            raw_line,
            path=path,
            line_number=line_number,
            previous_line_continues=(line_number > 1 and lines[line_number - 2].endswith("\\")),
            static_command_variables=static_command_variables,
        )
        if _MAKE_DEFINE_DIRECTIVE.match(raw_line):
            validate_make_execution_state(line, path=path, line_number=line_number)
            define_depth += 1
            continue
        if _MAKE_ENDEF_DIRECTIVE.match(raw_line):
            define_depth = max(0, define_depth - 1)
            continue
        if define_depth or raw_line.startswith("\t"):
            continue
        if _MAKE_CONDITIONAL_DIRECTIVE.match(line) or _MAKE_INCLUDE_DIRECTIVE.match(line):
            raise RequiredStatusChecksError(
                f"Makefile phony authority must be static: {path}; line={line_number}"
            )
        validate_make_execution_state(line, path=path, line_number=line_number)
        declaration = _STATIC_PHONY_DECLARATION.match(line)
        if declaration is None:
            continue
        target_text = declaration.group(1)
        declared_targets = target_text.split()
        if (
            not declared_targets
            or "$(" in target_text
            or "${" in target_text
            or target_text.endswith("\\")
            or any(_STATIC_PHONY_TARGET.fullmatch(target) is None for target in declared_targets)
        ):
            raise RequiredStatusChecksError(
                f"Makefile phony authority must be static: {path}; line={line_number}"
            )
        targets.update(declared_targets)
    return frozenset(targets)


def load_make_target_authority(path: Path) -> dict[str, MakeTargetAuthority]:
    try:
        path.stat()
    except OSError as exc:
        raise RequiredStatusChecksError(f"unable to load Makefile phony targets: {path}") from exc
    static_targets = _static_phony_targets(path)
    make_executable = shutil.which("make")
    if make_executable is None:
        raise RequiredStatusChecksError(f"unable to evaluate Makefile phony targets: {path}")
    make_environment = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"}
    try:
        result = subprocess.run(  # nosec B603
            (make_executable, *_MAKE_DATABASE_COMMAND[1:], "--file", path.name),
            cwd=path.parent,
            capture_output=True,
            check=False,
            encoding="utf-8",
            env=make_environment,
            errors="replace",
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise RequiredStatusChecksError(
            f"timed out evaluating Makefile phony targets: {path}"
        ) from exc
    except OSError as exc:
        raise RequiredStatusChecksError(
            f"unable to evaluate Makefile phony targets: {path}"
        ) from exc
    if result.returncode not in {0, 1}:
        raise RequiredStatusChecksError(f"unable to evaluate Makefile phony targets: {path}")
    effective_targets = _make_target_authority_from_files_section(
        _make_database_files_lines(result.stdout.splitlines(), path=path),
        path=path,
    )
    authority = {
        target: record
        for target, record in effective_targets.items()
        if record.phony and target in static_targets
    }
    if not authority:
        raise RequiredStatusChecksError(f"Makefile has no declared phony targets: {path}")
    return authority


def load_phony_make_targets(path: Path) -> frozenset[str]:
    return frozenset(load_make_target_authority(path))


def _validate_blocking_make_target(
    target: str,
    *,
    authority: Mapping[str, MakeTargetAuthority],
    path: Path,
    governed_repository_commands: Mapping[str, frozenset[str]],
    observed_repository_commands: dict[str, set[str]],
    validating: frozenset[str] = frozenset(),
) -> None:
    if target in validating:
        raise RequiredStatusChecksError(
            f"governed Make target execution cycle is not executable authority: "
            f"{path}; target={target}"
        )
    record = authority.get(target)
    if record is None:
        raise RequiredStatusChecksError(
            f"governed Make target lacks static phony authority: {path}; target={target}"
        )
    if record.recipes:
        repository_commands = validate_governed_recipe_commands(
            record.recipes,
            path=path,
            target=target,
            governed_repository_commands=governed_repository_commands,
        )
        if repository_commands:
            observed_repository_commands.setdefault(target, set()).update(repository_commands)
    if not record.recipes and not record.prerequisites:
        raise RequiredStatusChecksError(
            f"governed Make target has no executable control: {path}; target={target}"
        )
    next_validating = validating | {target}
    execution_dependencies = record.prerequisites + recursive_make_recipe_targets(
        record.recipes,
        path=path,
        target=target,
    )
    for prerequisite in execution_dependencies:
        _validate_blocking_make_target(
            prerequisite,
            authority=authority,
            path=path,
            governed_repository_commands=governed_repository_commands,
            observed_repository_commands=observed_repository_commands,
            validating=next_validating,
        )


def validate_make_targets_have_executable_authority(
    targets: frozenset[str],
    *,
    authority: Mapping[str, MakeTargetAuthority],
    path: Path,
    governed_repository_commands: Mapping[str, frozenset[str]] | None = None,
) -> None:
    """Require every workflow Make step to resolve to a real executable control."""

    command_contract = {} if governed_repository_commands is None else governed_repository_commands
    observed_repository_commands: dict[str, set[str]] = {}
    for target in sorted(targets):
        _validate_blocking_make_target(
            target,
            authority=authority,
            path=path,
            governed_repository_commands=command_contract,
            observed_repository_commands=observed_repository_commands,
        )
    observed_contract = {
        target: frozenset(commands) for target, commands in observed_repository_commands.items()
    }
    if observed_contract != command_contract:
        missing = sorted(
            f"{target}: {command}"
            for target, commands in observed_contract.items()
            for command in commands - command_contract.get(target, frozenset())
        )
        stale = sorted(
            f"{target}: {command}"
            for target, commands in command_contract.items()
            for command in commands - observed_contract.get(target, frozenset())
        )
        raise RequiredStatusChecksError(
            f"governed Make recipe command contract differs from execution closure: {path}; "
            f"missing={missing[:3]!r}; stale={stale[:3]!r}"
        )
