"""Guard the resource-bounded pytest-asyncio loop-scope contract."""

from __future__ import annotations

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
