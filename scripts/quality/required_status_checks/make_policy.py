from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from scripts.quality.required_status_checks.model import RequiredStatusChecksError

_BLOCKING_RECIPE_EXPANSIONS = frozenset(
    {
        "LATENCY_SEED_COMPLETION_TIMEOUT_SECONDS",
        "LOCAL_CERTIFICATION_BUILD_ARGUMENT",
        "LOCAL_RUNTIME_BUILD_ARGUMENT",
        "MAKE",
        "OPENAPI_ARTIFACT_DIR",
        "REPOSITORY_PYTHON",
    }
)
_GOVERNED_ASSIGNMENT_DECLARATIONS = frozenset(
    {
        "LATENCY_SEED_COMPLETION_TIMEOUT_SECONDS ?= 900",
        "CI_TRUTHY_VALUES := 1 true True TRUE yes Yes YES on On ON",
        "CI_IS_TRUE := $(filter $(CI_TRUTHY_VALUES),$(strip $(CI)))",
        "LOCAL_CERTIFICATION_BUILD_ARGUMENT = $(if $(CI_IS_TRUE),,--runtime-build)",
        "LOCAL_RUNTIME_BUILD_ARGUMENT = $(if $(CI_IS_TRUE),,--build)",
        "OPENAPI_ARTIFACT_DIR ?= output/openapi",
        "REPOSITORY_PYTHON := python scripts/development/repository_python.py",
        "TRANSACTION_RELEASE_OUTPUT ?= "
        "output/task-runs/transaction-processing-release-rehearsal.json",
        "TRANSACTION_RELEASE_PULL_IMAGES ?= false",
        "CI_GATES := lint no-alias-gate typecheck architecture-guard openapi-gate "
        "api-vocabulary-gate warning-gate migration-smoke test-pr-suites coverage-gate "
        "security-audit test-pr-runtime-gates",
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
_VARIABLE_DEFINE_DIRECTIVE = re.compile(r"^(?:(?:export|override|private)\s+)*define(?:\s|$)")
_VARIABLE_UNDEFINE_DIRECTIVE = re.compile(r"^(?:(?:export|override|private)\s+)*undefine(?:\s|$)")
_VPATH_DIRECTIVE = re.compile(r"^vpath(?:\s|$)")
_LOAD_DIRECTIVE = re.compile(r"^-?load(?:\s|$)")
_ENVIRONMENT_DIRECTIVE = re.compile(r"^(?:(?:override|private)\s+)*(?:export|unexport)(?:\s|$)")
_AUTHORITY_FUNCTION = re.compile(r"\$(?:\(|\{)\s*(?:call|eval|file|guile|shell)(?=[\s,)}\\]|$)")
_SAFE_DIAGNOSTIC_EXPANSION = re.compile(r"^\$\((?:error|info|warning)(?:\s|$).*\)$")
_IGNORED_RECIPE_PREFIX = re.compile(r"^[ \t@+]*-")
_DIRECT_RECIPE_VARIABLE = re.compile(r"^\$(?:\(([A-Za-z0-9_.-]+)\)|\{([A-Za-z0-9_.-]+)\})")
_SAFE_RECURSIVE_MAKE_COMMAND = re.compile(
    r"^\$(?:\(MAKE\)|\{MAKE\})[ \t]+(?P<target>[A-Za-z0-9_][A-Za-z0-9_.-]*)[ \t]*$"
)
_RECURSIVE_MAKE_EXPANSION = re.compile(r"\$(?:\(MAKE\)|\{MAKE\})")
_REPOSITORY_PYTHON_SCRIPT_COMMAND = re.compile(
    r"^\$\(REPOSITORY_PYTHON\)[ \t]+(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py(?:[ \t]|$)"
)
_REPOSITORY_PYTHON_MODULE_COMMAND = re.compile(
    r"^\$\(REPOSITORY_PYTHON\)[ \t]+-m[ \t]+[A-Za-z_][A-Za-z0-9_.-]*(?:[ \t]|$)"
)
_SAFE_RECIPE_PRECONDITION = re.compile(
    r"^\$\(if \$\(strip \$\([A-Za-z0-9_.-]+\)\),,"
    r"\$\(error [^)]*\)\)$"
)
_REPOSITORY_PYTHON_DECLARATION = (
    "REPOSITORY_PYTHON := python scripts/development/repository_python.py"
)
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


def _has_ungoverned_assignment(line: str) -> bool:
    """Require every GNU Make assignment to match repository-owned authority."""

    boundaries = (
        boundary
        for boundary in (
            _first_unexpanded_token(line, ("#",)),
            _first_unexpanded_token(line, (";",)),
        )
        if boundary is not None
    )
    declaration = line[: min(boundaries, default=len(line))]
    assignment = _first_unexpanded_token(declaration, _ASSIGNMENT_OPERATORS)
    return assignment is not None and line not in _GOVERNED_ASSIGNMENT_DECLARATIONS


def validate_make_authority_functions(lines: list[str], *, path: Path) -> None:
    """Reject direct or continued Make authority-function invocations."""

    for line_number, line in enumerate(lines, start=1):
        if _AUTHORITY_FUNCTION.search(line):
            raise RequiredStatusChecksError(
                f"Makefile phony authority must be static: {path}; line={line_number}"
            )


def static_recipe_command_variables(lines: list[str]) -> frozenset[str]:
    """Return the exact static variables admitted as recipe command identities."""

    variables = {"MAKE"}
    if lines.count(_REPOSITORY_PYTHON_DECLARATION) == 1:
        variables.add("REPOSITORY_PYTHON")
    return frozenset(variables)


def _make_recipe(line: str, *, path: Path, line_number: int) -> str | None:
    """Return the physical or inline recipe, rejecting stored recursive commands."""

    if line.startswith("\t"):
        return line[1:]
    comment = _first_unexpanded_token(line, ("#",))
    declaration = line if comment is None else line[:comment]
    inline_recipe = _first_unexpanded_token(declaration, (";",))
    target_separator = _first_unexpanded_token(declaration, (":",))
    assignment = _first_unexpanded_token(declaration, _ASSIGNMENT_OPERATORS)
    if (
        inline_recipe is not None
        and target_separator is not None
        and target_separator < inline_recipe
        and (assignment is None or assignment > inline_recipe)
    ):
        return declaration[inline_recipe + 1 :]
    if _RECURSIVE_MAKE_EXPANSION.search(declaration):
        raise RequiredStatusChecksError(
            f"Makefile execution state must be static: {path}; line={line_number}"
        )
    return None


def _has_shell_control_syntax(command: str) -> bool:
    """Return whether an unquoted shell operator can alter failure propagation."""

    quote: str | None = None
    escaped = False
    for index, character in enumerate(command):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            continue
        if quote == "'":
            continue
        if character == "`" or command.startswith("$$(", index):
            return True
        if quote is None and character in {";", "&", "|"}:
            return True
    return False


def _has_ungoverned_make_expansion(command: str) -> bool:
    """Return whether a recipe can expand a noncanonical Make value."""

    index = 0
    while index < len(command):
        expansion = command.find("$", index)
        if expansion < 0:
            return False
        if expansion + 1 >= len(command):
            return True
        marker = command[expansion + 1]
        if marker == "$":
            index = expansion + 2
            continue
        if marker not in {"(", "{"}:
            return True
        closer = ")" if marker == "(" else "}"
        end = command.find(closer, expansion + 2)
        if end < 0:
            return True
        variable = command[expansion + 2 : end]
        if variable not in _BLOCKING_RECIPE_EXPANSIONS:
            return True
        index = end + 1
    return False


def _logical_recipe_commands(
    recipes: tuple[str, ...],
    *,
    path: Path,
    target: str,
) -> tuple[str, ...]:
    """Reconstruct the shell commands formed by continued physical recipes."""

    commands: list[str] = []
    fragments: list[str] = []
    for recipe in recipes:
        logical_fragment = recipe.lstrip("\t") if fragments else recipe
        continued_recipe = logical_fragment.rstrip()
        continues = continued_recipe.endswith("\\")
        fragments.append(continued_recipe[:-1] if continues else logical_fragment)
        if continues:
            continue
        commands.append("".join(fragments))
        fragments = []
    if fragments:
        raise RequiredStatusChecksError(
            f"governed Make target has no complete executable control: {path}; target={target}"
        )
    return tuple(commands)


def validate_governed_recipe_commands(
    recipes: tuple[str, ...],
    *,
    path: Path,
    target: str,
    governed_repository_commands: Mapping[str, frozenset[str]] | None = None,
) -> frozenset[str]:
    """Require blocking targets to use fail-fast, statically bounded commands."""

    command_count = 0
    repository_commands: set[str] = set()
    target_repository_commands = (
        frozenset()
        if governed_repository_commands is None
        else governed_repository_commands.get(target, frozenset())
    )
    for recipe in _logical_recipe_commands(recipes, path=path, target=target):
        command = recipe.lstrip(" \t@+")
        make_control = bool(
            _SAFE_DIAGNOSTIC_EXPANSION.fullmatch(command)
            or _SAFE_RECIPE_PRECONDITION.fullmatch(command)
        )
        if not make_control and _has_ungoverned_make_expansion(command):
            raise RequiredStatusChecksError(
                f"blocking Make target recipe uses a noncanonical Make expansion: "
                f"{path}; target={target}"
            )
        if not make_control and _has_shell_control_syntax(command):
            raise RequiredStatusChecksError(
                f"blocking Make target recipe must not use shell control syntax: "
                f"{path}; target={target}"
            )
        script_identity = _REPOSITORY_PYTHON_SCRIPT_COMMAND.match(command)
        module_identity = _REPOSITORY_PYTHON_MODULE_COMMAND.match(command)
        repository_python_identity = bool(script_identity or module_identity)
        if repository_python_identity:
            repository_commands.add(command)
        canonical_identity = bool(
            make_control
            or (repository_python_identity and command in target_repository_commands)
            or _SAFE_RECURSIVE_MAKE_COMMAND.fullmatch(command)
        )
        if not canonical_identity:
            raise RequiredStatusChecksError(
                f"blocking Make target must use a canonical direct command identity: "
                f"{path}; target={target}"
            )
        command_count += 1
    if command_count == 0:
        raise RequiredStatusChecksError(
            f"governed Make target has no complete executable control: {path}; target={target}"
        )
    return frozenset(repository_commands)


def recursive_make_recipe_targets(
    recipes: tuple[str, ...],
    *,
    path: Path,
    target: str,
) -> tuple[str, ...]:
    """Return statically named recursive-Make commands from validated recipes."""

    targets: list[str] = []
    for recipe in _logical_recipe_commands(recipes, path=path, target=target):
        command = recipe.lstrip(" \t@+")
        recursive_make = _SAFE_RECURSIVE_MAKE_COMMAND.fullmatch(command)
        if recursive_make is not None:
            targets.append(recursive_make.group("target"))
    return tuple(targets)


def validate_make_recipe_failure_propagation(
    line: str,
    *,
    path: Path,
    line_number: int,
    previous_line_continues: bool,
    static_command_variables: frozenset[str],
) -> None:
    """Reject ignored-error prefixes at physical and inline recipe starts."""

    recipe = _make_recipe(line, path=path, line_number=line_number)
    if recipe is None:
        return
    if previous_line_continues:
        return
    if _IGNORED_RECIPE_PREFIX.match(recipe):
        raise RequiredStatusChecksError(
            f"Makefile execution state must be static: {path}; line={line_number}"
        )
    command = recipe.lstrip(" \t@+")
    if (
        not command.startswith("$")
        or _SAFE_DIAGNOSTIC_EXPANSION.fullmatch(command)
        or _SAFE_RECIPE_PRECONDITION.fullmatch(command)
    ):
        return
    direct_variable = _DIRECT_RECIPE_VARIABLE.match(command)
    variable_name = (
        None
        if direct_variable is None
        else next(group for group in direct_variable.groups() if group is not None)
    )
    if variable_name not in static_command_variables or (
        variable_name == "MAKE" and _SAFE_RECURSIVE_MAKE_COMMAND.fullmatch(command) is None
    ):
        raise RequiredStatusChecksError(
            f"Makefile execution state must be static: {path}; line={line_number}"
        )


def validate_make_execution_state(line: str, *, path: Path, line_number: int) -> None:
    """Reject Make syntax that can alter parsing or execution of governed targets."""

    mutable_state = (
        (line.endswith("\\") and not line.startswith(".PHONY:"))
        or _has_ungoverned_assignment(line)
        or _has_expansion_dependent_declaration(line)
        or _has_execution_special_target(line)
        or _VARIABLE_UNDEFINE_DIRECTIVE.match(line) is not None
        or any(
            pattern.match(line)
            for pattern in (
                _ENVIRONMENT_DIRECTIVE,
                _LOAD_DIRECTIVE,
                _VARIABLE_DEFINE_DIRECTIVE,
                _VPATH_DIRECTIVE,
            )
        )
    )
    if mutable_state:
        raise RequiredStatusChecksError(
            f"Makefile execution state must be static: {path}; line={line_number}"
        )
