"""Guard the resource-bounded pytest-asyncio loop-scope contract."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path


def test_asyncio_loop_scopes_bound_windows_socket_churn() -> None:
    """Keep async fixtures and tests on one bounded loop per test module."""
    configuration = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    pytest_options = configuration["tool"]["pytest"]["ini_options"]

    assert pytest_options["asyncio_default_fixture_loop_scope"] == "module"
    assert pytest_options["asyncio_default_test_loop_scope"] == "module"
    assert all(
        "asyncio_default_fixture_loop_scope" not in warning
        for warning in pytest_options["filterwarnings"]
    )


def test_unit_tests_delegate_event_loop_ownership_to_pytest_asyncio() -> None:
    """Prevent nested runners from replacing module-scoped pytest event loops."""

    offenders: list[str] = []
    for path in sorted(Path("tests/unit").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "asyncio"
                and node.func.attr == "run"
            ):
                offenders.append(f"{path.as_posix()}:{node.lineno}")

    assert offenders == [], (
        "Unit tests must use pytest.mark.asyncio and await directly so pytest-asyncio owns and "
        f"closes the configured event loop: {offenders}"
    )
