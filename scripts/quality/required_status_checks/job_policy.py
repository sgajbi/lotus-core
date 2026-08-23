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
_SAFE_ENFORCEMENT_SHELLS = frozenset({"bash"})
_SHELL_FAILURE_SUPPRESSION = re.compile(
    r"(?:\|\|\s*(?:true|:)(?:\s|$)|(?:^|[;&]\s*)set\s+\+e(?:\s|$)|"
    r"\bmake\b[^\n]*(?:\s-(?:n|q)(?:\s|$)|\s--(?:dry-run|just-print|recon|question)(?:\s|$))|"
    r"(?<![&<>])&(?![&>])|\b(?:nohup|setsid|coproc|disown)\b)",
    re.MULTILINE,
)


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
    if isinstance(action, str) and action.startswith(_CONDITIONAL_AUXILIARY_ACTION_PREFIXES):
        raise RequiredStatusChecksError(
            f"blocking workflow enforce step must not be an auxiliary action: {context_text}; "
            f"step={step_name!r}"
        )


def _validate_enforcement_shell(shell: object, *, context_text: str) -> None:
    if not isinstance(shell, str) or shell not in _SAFE_ENFORCEMENT_SHELLS:
        raise RequiredStatusChecksError(
            f"blocking workflow enforce step uses an unsupported shell: {context_text}; "
            f"shell={shell!r}"
        )


def _effective_enforcement_shell(
    step: Mapping[str, Any], *, default_shell: str | None, context_text: str
) -> str | None:
    if "shell" not in step:
        return default_shell
    return require_non_empty_string(
        step.get("shell"), field=f"blocking workflow enforce step shell: {context_text}"
    )


def _validate_blocking_step(
    step: object, *, contexts: tuple[str, ...], default_shell: str | None
) -> bool:
    context_text = ", ".join(contexts)
    if not isinstance(step, dict):
        raise RequiredStatusChecksError(
            f"blocking workflow job step must be an object: {context_text}"
        )
    step_name = step.get("name", "<unnamed step>")
    if "continue-on-error" in step:
        raise RequiredStatusChecksError(
            f"blocking workflow steps must not tolerate failure: {context_text}; step={step_name!r}"
        )
    _validate_step_condition(step, context_text=context_text, step_name=step_name)
    if step.get("id") != "enforce":
        return False
    _validate_enforcement_action(step, context_text=context_text, step_name=step_name)
    executable = step.get("run") or step.get("uses")
    if not isinstance(executable, str):
        raise RequiredStatusChecksError(
            f"blocking workflow enforce step must execute run or uses: {context_text}"
        )
    run_command = step.get("run")
    if isinstance(run_command, str):
        effective_shell = _effective_enforcement_shell(
            step, default_shell=default_shell, context_text=context_text
        )
        _validate_enforcement_shell(effective_shell, context_text=context_text)
        if _SHELL_FAILURE_SUPPRESSION.search(run_command):
            raise RequiredStatusChecksError(
                "blocking workflow enforce step suppresses command execution or failure: "
                f"{context_text}"
            )
    return True


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
    job: Mapping[str, Any], *, contexts: tuple[str, ...], workflow_shell: str | None
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
    enforcement_steps = sum(
        _validate_blocking_step(
            step,
            contexts=contexts,
            default_shell=job_shell or workflow_shell,
        )
        for step in steps or ()
    )
    if enforcement_steps != 1:
        raise RequiredStatusChecksError(
            "blocking workflow jobs must declare exactly one unconditional id: enforce step: "
            f"{context_text}; observed={enforcement_steps}"
        )
