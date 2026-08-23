from __future__ import annotations

from typing import Any, Mapping

from scripts.quality.required_status_checks.model import RequiredStatusChecksError

_ACTION_INPUT_KEYS = {
    "actions/cache@v5": frozenset({"key", "path", "restore-keys"}),
    "actions/cache/restore@v5": frozenset({"key", "path", "restore-keys"}),
    "actions/cache/save@v5": frozenset({"key", "path"}),
    "actions/checkout@v6": frozenset({"fetch-depth", "path", "persist-credentials", "repository"}),
    "actions/download-artifact@v8": frozenset({"merge-multiple", "name", "path", "pattern"}),
    "actions/setup-node@v6": frozenset({"cache", "cache-dependency-path", "node-version"}),
    "actions/setup-python@v6": frozenset({"cache", "python-version"}),
    "actions/upload-artifact@v7": frozenset(
        {"compression-level", "if-no-files-found", "name", "path", "retention-days"}
    ),
    "docker/setup-buildx-action@v4": frozenset(),
    "reviewdog/action-actionlint@v1": frozenset(),
}
_AUDITED_ACTIONS = frozenset(_ACTION_INPUT_KEYS)
_ENFORCEMENT_ACTIONS = frozenset({"reviewdog/action-actionlint@v1"})
_AUXILIARY_ACTIONS = _AUDITED_ACTIONS - _ENFORCEMENT_ACTIONS
_CONDITIONAL_AUXILIARY_ACTIONS = frozenset(
    {"actions/cache/save@v5", "actions/checkout@v6", "actions/upload-artifact@v7"}
)


def is_conditional_auxiliary_action(action: object) -> bool:
    return isinstance(action, str) and action in _CONDITIONAL_AUXILIARY_ACTIONS


def _require_relative_output_path(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RequiredStatusChecksError(f"blocking workflow action {field} must be non-empty")
    for raw_path in value.splitlines():
        if "${{" in raw_path:
            raise RequiredStatusChecksError(
                f"blocking workflow action {field} must not contain expressions: {raw_path!r}"
            )
        path = raw_path.strip().replace("\\", "/")
        if not path.startswith("output/") or "/../" in f"/{path}/" or path.endswith("/.."):
            raise RequiredStatusChecksError(
                f"blocking workflow action {field} must stay under output/: {raw_path!r}"
            )


def _validate_checkout_inputs(inputs: Mapping[str, Any]) -> None:
    if "fetch-depth" in inputs and inputs["fetch-depth"] != 0:
        raise RequiredStatusChecksError("blocking workflow checkout fetch-depth must be 0")
    if "persist-credentials" in inputs and inputs["persist-credentials"] is not False:
        raise RequiredStatusChecksError(
            "blocking workflow checkout persist-credentials must be false"
        )
    repository = inputs.get("repository")
    path = inputs.get("path")
    if repository is None and path is not None:
        raise RequiredStatusChecksError("blocking workflow checkout path requires repository")
    if repository is not None and (
        repository != "sgajbi/lotus-platform"
        or path != "lotus-platform"
        or inputs.get("persist-credentials") is not False
    ):
        raise RequiredStatusChecksError(
            "blocking workflow alternate checkout must be the credential-free platform checkout"
        )


def _validate_cache_inputs(inputs: Mapping[str, Any]) -> None:
    if inputs.get("path") not in {".buildx-cache", ".cache/dependency-health"}:
        raise RequiredStatusChecksError("blocking workflow cache path is not audited")
    if not isinstance(inputs.get("key"), str) or not inputs["key"].strip():
        raise RequiredStatusChecksError("blocking workflow cache key must be non-empty")
    if "restore-keys" in inputs and (
        not isinstance(inputs["restore-keys"], str) or not inputs["restore-keys"].strip()
    ):
        raise RequiredStatusChecksError("blocking workflow cache restore-keys must be non-empty")


def _validate_artifact_inputs(action: str, inputs: Mapping[str, Any]) -> None:
    name = inputs.get("name")
    if not isinstance(name, str) or not name.strip() or "\n" in name:
        raise RequiredStatusChecksError(
            "blocking workflow artifact name must be one non-empty line"
        )
    _require_relative_output_path(inputs.get("path"), field="artifact path")
    if action == "actions/download-artifact@v8":
        if "pattern" in inputs and (
            not isinstance(inputs["pattern"], str) or not inputs["pattern"].strip()
        ):
            raise RequiredStatusChecksError("blocking workflow artifact pattern must be non-empty")
        if "merge-multiple" in inputs and not isinstance(inputs["merge-multiple"], bool):
            raise RequiredStatusChecksError(
                "blocking workflow artifact merge-multiple must be boolean"
            )
        return
    if "if-no-files-found" in inputs and inputs["if-no-files-found"] not in {
        "error",
        "ignore",
        "warn",
    }:
        raise RequiredStatusChecksError(
            "blocking workflow artifact if-no-files-found value is not audited"
        )
    _validate_bounded_integer(inputs, key="retention-days", minimum=1, maximum=30)
    _validate_bounded_integer(inputs, key="compression-level", minimum=0, maximum=9)


def _validate_bounded_integer(
    inputs: Mapping[str, Any], *, key: str, minimum: int, maximum: int
) -> None:
    if key not in inputs:
        return
    value = inputs[key]
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise RequiredStatusChecksError(
            f"blocking workflow artifact {key} must be between {minimum} and {maximum}"
        )


def _validate_setup_inputs(action: str, inputs: Mapping[str, Any], *, runner: str) -> None:
    if action == "actions/setup-python@v6":
        expected_version = "3.11" if runner == "windows-latest" else "${{ env.PYTHON_VERSION }}"
        if inputs.get("python-version") != expected_version:
            raise RequiredStatusChecksError("blocking workflow setup-python version is not audited")
        if "cache" in inputs and inputs["cache"] != "pip":
            raise RequiredStatusChecksError("blocking workflow setup-python cache must be pip")
        return
    if inputs.get("node-version") != "${{ env.NODE_VERSION }}":
        raise RequiredStatusChecksError("blocking workflow setup-node version is not audited")
    if inputs.get("cache") != "npm" or inputs.get("cache-dependency-path") != (
        "tools/api_governance/package-lock.json"
    ):
        raise RequiredStatusChecksError("blocking workflow setup-node cache inputs are not audited")


def _action_inputs(step: Mapping[str, Any], *, action: str) -> Mapping[str, Any]:
    raw_inputs = step.get("with")
    if raw_inputs is None:
        inputs: Mapping[str, Any] = {}
    elif not isinstance(raw_inputs, dict):
        raise RequiredStatusChecksError("blocking workflow action with must be an object")
    else:
        inputs = raw_inputs
    if not all(isinstance(key, str) for key in inputs):
        raise RequiredStatusChecksError("blocking workflow action with keys must be strings")
    unknown_keys = sorted(set(inputs) - _ACTION_INPUT_KEYS[action])
    if unknown_keys:
        raise RequiredStatusChecksError(
            f"blocking workflow action uses unsupported with keys: {unknown_keys!r}"
        )
    return inputs


def _validate_action_inputs(action: str, step: Mapping[str, Any], *, runner: str) -> None:
    inputs = _action_inputs(step, action=action)
    if action == "actions/checkout@v6":
        _validate_checkout_inputs(inputs)
    elif action in {"actions/cache@v5", "actions/cache/restore@v5", "actions/cache/save@v5"}:
        _validate_cache_inputs(inputs)
    elif action in {"actions/download-artifact@v8", "actions/upload-artifact@v7"}:
        _validate_artifact_inputs(action, inputs)
    elif action in {"actions/setup-node@v6", "actions/setup-python@v6"}:
        _validate_setup_inputs(action, inputs, runner=runner)


def validate_step_action(
    step: Mapping[str, Any],
    *,
    enforcement: bool,
    context_text: str,
    step_name: object,
    runner: str,
) -> None:
    action = step.get("uses")
    admitted_actions = _ENFORCEMENT_ACTIONS if enforcement else _AUXILIARY_ACTIONS
    if action is not None and (not isinstance(action, str) or action not in admitted_actions):
        raise RequiredStatusChecksError(
            "blocking workflow step uses an unaudited action reference: "
            f"{context_text}; step={step_name!r}; uses={action!r}"
        )
    if isinstance(action, str):
        _validate_action_inputs(action, step, runner=runner)
