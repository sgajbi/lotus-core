from __future__ import annotations

import re
from typing import Any, Mapping

from scripts.quality.required_status_checks.model import (
    RequiredStatusChecksError,
    require_non_empty_string,
)

_CONDITIONAL_AUXILIARY_ACTION_PREFIXES = (
    "actions/cache/save@",
    "actions/checkout@",
    "actions/upload-artifact@",
)
_AUXILIARY_ACTION_PREFIXES = (
    "actions/cache@",
    "actions/cache/restore@",
    "actions/cache/save@",
    "actions/checkout@",
    "actions/download-artifact@",
    "actions/setup-node@",
    "actions/setup-python@",
    "actions/upload-artifact@",
    "docker/setup-buildx-action@",
)
_ENFORCEMENT_ACTION_PREFIXES = ("reviewdog/action-actionlint@",)
_SAFE_ENFORCEMENT_SHELLS = frozenset({"bash"})
_DISABLING_ENVIRONMENT_VARIABLES = frozenset(
    {"BASH_ENV", "GNUMAKEFLAGS", "MAKEFILES", "MAKEFLAGS", "MFLAGS"}
)
_MAKE_TARGET_TEXT = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
_MAKE_TARGET = re.compile(rf"^{_MAKE_TARGET_TEXT}$")
_STATIC_MAKE_COMMAND = re.compile(rf"^make[ \t]+({_MAKE_TARGET_TEXT})$")
_MATRIX_MAKE_COMMAND = re.compile(
    r"^make[ \t]+\$\{\{[ \t]*matrix\.([A-Za-z_][A-Za-z0-9_]*)[ \t]*\}\}$"
)
_BARE_RUN_COMMAND = re.compile(
    rf"^(?:make[ \t]+(?:{_MAKE_TARGET_TEXT}|"
    r"\$\{\{[ \t]*matrix\.[A-Za-z_][A-Za-z0-9_]*[ \t]*\}\})|"
    r"python[ \t]+scripts/development/update_(?:ci_tooling|shared_runtime)_lock\.py"
    r"[ \t]+--check[ \t]+--platform[ \t]+windows)$"
)
_RUNTIME_IMAGE_AUTHORITY = "LOTUS_RUNTIME_IMAGE_SET_VERIFIED"
_RUNTIME_IMAGE_VERIFY_COMMAND = "make runtime-image-set-load-verify"


def default_run_shell(configuration: Mapping[str, Any], *, scope: str) -> str | None:
    defaults = configuration.get("defaults")
    if defaults is None:
        return None
    if not isinstance(defaults, dict):
        raise RequiredStatusChecksError(f"workflow defaults must be an object: {scope}")
    run_defaults = defaults.get("run")
    if run_defaults is None:
        return None
    if not isinstance(run_defaults, dict):
        raise RequiredStatusChecksError(f"workflow run defaults must be an object: {scope}")
    if "working-directory" in run_defaults:
        raise RequiredStatusChecksError(
            f"blocking workflow run steps must execute at the repository root: {scope}"
        )
    shell = run_defaults.get("shell")
    if shell is None:
        return None
    return require_non_empty_string(shell, field=f"{scope} default run shell")


def _validate_step_condition(
    step: Mapping[str, Any], *, context_text: str, step_name: object
) -> None:
    if "if" not in step:
        return
    if step.get("id") == "enforce":
        raise RequiredStatusChecksError(
            f"blocking workflow enforcement steps must be unconditional: {context_text}; "
            f"step={step_name!r}"
        )
    action = step.get("uses")
    if not isinstance(action, str) or not action.startswith(_CONDITIONAL_AUXILIARY_ACTION_PREFIXES):
        raise RequiredStatusChecksError(
            f"blocking workflow enforcement steps must be unconditional: {context_text}; "
            f"step={step_name!r}"
        )


def _validate_enforcement_action(
    step: Mapping[str, Any], *, context_text: str, step_name: object
) -> None:
    action = step.get("uses")
    if action is not None and (
        not isinstance(action, str) or not action.startswith(_ENFORCEMENT_ACTION_PREFIXES)
    ):
        raise RequiredStatusChecksError(
            f"blocking workflow enforce step uses an unsupported action: {context_text}; "
            f"step={step_name!r}"
        )


def _validate_auxiliary_action(
    step: Mapping[str, Any], *, context_text: str, step_name: object
) -> None:
    action = step.get("uses")
    if action is not None and (
        not isinstance(action, str) or not action.startswith(_AUXILIARY_ACTION_PREFIXES)
    ):
        raise RequiredStatusChecksError(
            f"blocking workflow step uses an unsupported auxiliary action: {context_text}; "
            f"step={step_name!r}"
        )


def effective_environment(
    configuration: Mapping[str, Any],
    *,
    inherited: Mapping[str, Any] | None = None,
    scope: str,
) -> dict[str, Any]:
    environment = configuration.get("env")
    effective = dict(inherited or {})
    if environment is None:
        return effective
    if not isinstance(environment, dict):
        raise RequiredStatusChecksError(
            f"blocking workflow enforcement environment must be an object: {scope}"
        )
    effective.update(environment)
    return effective


def _validate_run_environment(environment: Mapping[str, Any], *, context_text: str) -> None:
    disabling_variables = sorted(_DISABLING_ENVIRONMENT_VARIABLES & environment.keys())
    if disabling_variables:
        raise RequiredStatusChecksError(
            "blocking workflow run step environment injects a disabling variable: "
            f"{context_text}; variables={disabling_variables!r}"
        )


def _validate_run_shell(shell: object, *, context_text: str) -> None:
    if not isinstance(shell, str) or shell not in _SAFE_ENFORCEMENT_SHELLS:
        raise RequiredStatusChecksError(
            f"blocking workflow run step uses an unsupported shell: {context_text}; shell={shell!r}"
        )


def _run_make_targets(
    job: Mapping[str, Any], *, run_command: str, context_text: str
) -> tuple[str, ...]:
    static_target = _STATIC_MAKE_COMMAND.fullmatch(run_command)
    if static_target is not None:
        return (static_target.group(1),)
    expression = _MATRIX_MAKE_COMMAND.fullmatch(run_command)
    if expression is None:
        return ()
    strategy = job.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    include = matrix.get("include") if isinstance(matrix, dict) else None
    if not isinstance(include, list) or not include:
        raise RequiredStatusChecksError(
            f"blocking workflow matrix run step has no include rows: {context_text}"
        )
    matrix_key = expression.group(1)
    targets: list[str] = []
    for row_index, row in enumerate(include):
        value = row.get(matrix_key) if isinstance(row, dict) else None
        if not isinstance(value, str) or _MAKE_TARGET.fullmatch(value) is None:
            raise RequiredStatusChecksError(
                "blocking workflow matrix run target must be a bare Make target: "
                f"{context_text}; matrix.{matrix_key}; row={row_index}"
            )
        targets.append(value)
    return tuple(targets)


def _validate_run_make_targets(
    job: Mapping[str, Any],
    *,
    run_command: str,
    context_text: str,
    phony_make_targets: frozenset[str],
) -> None:
    targets = _run_make_targets(
        job,
        run_command=run_command,
        context_text=context_text,
    )
    undeclared_targets = sorted(set(targets) - phony_make_targets)
    if undeclared_targets:
        raise RequiredStatusChecksError(
            "blocking workflow run target is not a declared phony Make target: "
            + ", ".join(undeclared_targets)
        )


def _effective_run_shell(
    step: Mapping[str, Any], *, default_shell: str | None, context_text: str
) -> str | None:
    if "shell" not in step:
        return default_shell
    return require_non_empty_string(
        step.get("shell"), field=f"blocking workflow run step shell: {context_text}"
    )


def _validate_blocking_step(
    step: object,
    *,
    job: Mapping[str, Any],
    contexts: tuple[str, ...],
    phony_make_targets: frozenset[str],
    default_shell: str | None,
    default_environment: Mapping[str, Any],
    runtime_image_verified: bool,
) -> tuple[bool, bool]:
    context_text = ", ".join(contexts)
    if not isinstance(step, dict):
        raise RequiredStatusChecksError(
            f"blocking workflow job step must be an object: {context_text}"
        )
    step_name = step.get("name", "<unnamed step>")
    run_command = step.get("run")
    action = step.get("uses")
    if run_command is not None and not isinstance(run_command, str):
        raise RequiredStatusChecksError(
            f"blocking workflow step run must be a string: {context_text}; step={step_name!r}"
        )
    if action is not None and not isinstance(action, str):
        raise RequiredStatusChecksError(
            f"blocking workflow step uses must be a string: {context_text}; step={step_name!r}"
        )
    if run_command is not None and action is not None:
        raise RequiredStatusChecksError(
            f"blocking workflow step cannot define both run and uses: {context_text}; "
            f"step={step_name!r}"
        )
    if "continue-on-error" in step:
        raise RequiredStatusChecksError(
            f"blocking workflow steps must not tolerate failure: {context_text}; step={step_name!r}"
        )
    _validate_step_condition(step, context_text=context_text, step_name=step_name)
    is_enforcement = step.get("id") == "enforce"
    if is_enforcement:
        _validate_enforcement_action(step, context_text=context_text, step_name=step_name)
    else:
        _validate_auxiliary_action(step, context_text=context_text, step_name=step_name)
    if "working-directory" in step:
        raise RequiredStatusChecksError(
            f"blocking workflow run step must execute at the repository root: {context_text}"
        )
    executable = step.get("run") or step.get("uses")
    if not isinstance(executable, str):
        raise RequiredStatusChecksError(
            f"blocking workflow step must execute run or uses: {context_text}"
        )
    if isinstance(run_command, str):
        environment = effective_environment(
            step,
            inherited=default_environment,
            scope=f"blocking step {context_text}",
        )
        _validate_run_environment(environment, context_text=context_text)
        effective_shell = _effective_run_shell(
            step, default_shell=default_shell, context_text=context_text
        )
        _validate_run_shell(effective_shell, context_text=context_text)
        if _BARE_RUN_COMMAND.fullmatch(run_command) is None:
            raise RequiredStatusChecksError(
                f"blocking workflow run step must be a single bare command: {context_text}; "
                f"step={step_name!r}"
            )
        _validate_run_make_targets(
            job,
            run_command=run_command,
            context_text=context_text,
            phony_make_targets=phony_make_targets,
        )
        grants_runtime_authority = _RUNTIME_IMAGE_AUTHORITY in environment
        if grants_runtime_authority and environment[_RUNTIME_IMAGE_AUTHORITY] != "true":
            raise RequiredStatusChecksError(
                "blocking workflow runtime image authority must be exact string true: "
                f"{context_text}; step={step_name!r}"
            )
        if grants_runtime_authority and not runtime_image_verified:
            raise RequiredStatusChecksError(
                "blocking workflow step grants runtime image authority before verification: "
                f"{context_text}; step={step_name!r}"
            )
        runtime_image_verified = (
            runtime_image_verified or run_command == _RUNTIME_IMAGE_VERIFY_COMMAND
        )
    return is_enforcement, runtime_image_verified


def dependency_ids(job: Mapping[str, Any], *, contexts: tuple[str, ...]) -> tuple[str, ...]:
    needs = job.get("needs")
    if needs is None:
        return ()
    if isinstance(needs, str):
        dependency_values = (needs,)
    elif isinstance(needs, list) and all(isinstance(value, str) for value in needs):
        dependency_values = tuple(needs)
    else:
        raise RequiredStatusChecksError(
            f"blocking workflow job needs must be a string or string list: {', '.join(contexts)}"
        )
    if len(dependency_values) != len(set(dependency_values)) or any(
        not value for value in dependency_values
    ):
        raise RequiredStatusChecksError(
            f"blocking workflow job needs must be unique non-empty job ids: {', '.join(contexts)}"
        )
    return dependency_values


def validate_blocking_job(
    job: Mapping[str, Any],
    *,
    contexts: tuple[str, ...],
    phony_make_targets: frozenset[str],
    workflow_shell: str | None,
    workflow_environment: Mapping[str, Any],
) -> None:
    context_text = ", ".join(contexts)
    if "if" in job:
        raise RequiredStatusChecksError(
            f"blocking workflow jobs must be unconditional: {context_text}"
        )
    if "continue-on-error" in job:
        raise RequiredStatusChecksError(
            f"blocking workflow jobs must not tolerate failure: {context_text}"
        )
    steps = job.get("steps")
    if steps is not None and not isinstance(steps, list):
        raise RequiredStatusChecksError(
            f"blocking workflow job steps must be a list: {context_text}"
        )
    job_shell = default_run_shell(job, scope=f"blocking job {context_text}")
    job_environment = effective_environment(
        job,
        inherited=workflow_environment,
        scope=f"blocking job {context_text}",
    )
    enforcement_steps = 0
    runtime_image_verified = False
    for step in steps or ():
        is_enforcement, runtime_image_verified = _validate_blocking_step(
            step,
            job=job,
            contexts=contexts,
            phony_make_targets=phony_make_targets,
            default_shell=job_shell or workflow_shell,
            default_environment=job_environment,
            runtime_image_verified=runtime_image_verified,
        )
        enforcement_steps += int(is_enforcement)
    if enforcement_steps != 1:
        raise RequiredStatusChecksError(
            "blocking workflow jobs must declare exactly one unconditional id: enforce step: "
            f"{context_text}; observed={enforcement_steps}"
        )
