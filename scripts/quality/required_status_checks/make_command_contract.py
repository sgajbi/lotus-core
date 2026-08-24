from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

from scripts.quality.required_status_checks.model import RequiredStatusChecksError

DEFAULT_MAKE_COMMAND_CONTRACT_PATH = Path("contracts/ci/governed-make-recipe-commands.v1.json")
_SCHEMA_VERSION = "governed-make-recipe-commands.v1"
_TARGET_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def _read_contract(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RequiredStatusChecksError(
            f"unable to load governed Make recipe command contract: {path}"
        ) from exc


def _contract_targets(path: Path, raw: object) -> dict[object, object]:
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "targets"}:
        raise RequiredStatusChecksError(
            f"governed Make recipe command contract has an unexpected shape: {path}"
        )
    if raw["schema_version"] != _SCHEMA_VERSION:
        raise RequiredStatusChecksError(
            f"unsupported governed Make recipe command contract schema: {path}"
        )
    raw_targets = raw["targets"]
    if not isinstance(raw_targets, dict) or list(raw_targets) != sorted(raw_targets):
        raise RequiredStatusChecksError(
            f"governed Make recipe command contract targets must be an object: {path}"
        )
    return raw_targets


def _target_commands(
    path: Path, target: object, raw_commands: object
) -> tuple[str, frozenset[str]]:
    if not isinstance(target, str) or _TARGET_NAME.fullmatch(target) is None:
        raise RequiredStatusChecksError(
            f"governed Make recipe command contract target is noncanonical: "
            f"{path}; target={target!r}"
        )
    if not isinstance(raw_commands, list) or not raw_commands:
        raise RequiredStatusChecksError(
            f"governed Make recipe command contract target is noncanonical: "
            f"{path}; target={target!r}"
        )
    if any(
        not isinstance(command, str) or not command or command != command.strip()
        for command in raw_commands
    ):
        raise RequiredStatusChecksError(
            f"governed Make recipe command contract target is noncanonical: "
            f"{path}; target={target!r}"
        )
    if raw_commands != sorted(raw_commands) or len(raw_commands) != len(set(raw_commands)):
        raise RequiredStatusChecksError(
            f"governed Make recipe command contract target is noncanonical: "
            f"{path}; target={target!r}"
        )
    return target, frozenset(raw_commands)


def load_governed_make_recipe_commands(path: Path) -> Mapping[str, frozenset[str]]:
    """Load exact repository Python commands admitted for each governed Make target."""

    raw_targets = _contract_targets(path, _read_contract(path))
    targets: dict[str, frozenset[str]] = {}
    for target, raw_commands in raw_targets.items():
        canonical_target, commands = _target_commands(path, target, raw_commands)
        targets[canonical_target] = commands
    return targets
