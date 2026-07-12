"""Prevent validation drivers from recreating unmanaged Compose lifecycle commands."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MANAGED_DRIVERS = (
    REPO_ROOT / "scripts" / "operations" / "latency_profile.py",
    REPO_ROOT / "scripts" / "operations" / "performance_load_gate.py",
    REPO_ROOT / "scripts" / "validation" / "docker_endpoint_smoke.py",
    REPO_ROOT / "scripts" / "validation" / "institutional_completion_gate.py",
)
FORBIDDEN_LIFECYCLE_OPERATIONS = frozenset({"up", "down", "logs"})


def _literal_command_parts(node: ast.List | ast.Tuple) -> tuple[str, ...]:
    return tuple(
        element.value
        for element in node.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    )


def test_compose_validation_drivers_use_one_managed_lifecycle_owner() -> None:
    for path in MANAGED_DRIVERS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        assert "prepare_managed_compose_run" in source

        unmanaged_commands = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.List, ast.Tuple)):
                continue
            parts = _literal_command_parts(node)
            if parts[:2] != ("docker", "compose"):
                continue
            if FORBIDDEN_LIFECYCLE_OPERATIONS.intersection(parts[2:]):
                unmanaged_commands.append((node.lineno, parts))

        assert unmanaged_commands == [], (
            f"{path.relative_to(REPO_ROOT)} reconstructs unmanaged Compose lifecycle commands: "
            f"{unmanaged_commands}"
        )
