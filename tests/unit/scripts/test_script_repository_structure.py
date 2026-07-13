"""Enforce descriptive ownership and naming for repository automation."""

import re
from pathlib import Path

SCRIPT_ROOT_FILES = {"README.md", "__init__.py"}
SCRIPT_AREAS = {
    "development",
    "generators",
    "operations",
    "quality",
    "release",
    "transaction_processing",
    "validation",
}
RFC_TRACKING_SCRIPT_NAMES = {
    "rfc_status_ledger_guard.py",
    "rfc0083_closure_guard.py",
}
FORBIDDEN_GENERIC_NAMES = {"common.py", "helpers.py", "utils.py"}


def test_scripts_are_owned_by_a_documented_area() -> None:
    script_root = Path("scripts")

    assert {path.name for path in script_root.iterdir() if path.is_file()} == SCRIPT_ROOT_FILES
    assert {
        path.name for path in script_root.iterdir() if path.is_dir() and path.name != "__pycache__"
    } == SCRIPT_AREAS


def test_script_names_are_domain_descriptive() -> None:
    script_files = tuple(Path("scripts").glob("*/*.py"))

    assert not {path.name for path in script_files} & FORBIDDEN_GENERIC_NAMES
    assert not {
        path.name for path in script_files if re.match(r"(?:issue|gh)[-_]?\d+", path.stem, re.I)
    }
    assert {
        path.name for path in script_files if path.name.lower().startswith("rfc")
    } == RFC_TRACKING_SCRIPT_NAMES


def test_workflows_do_not_invoke_scripts_through_retired_root_paths() -> None:
    script_names = {
        path.name for path in Path("scripts").glob("*/*.py") if path.name != "__init__.py"
    }
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in Path(".github/workflows").glob("*.yml")
    )

    assert not {name for name in script_names if f"scripts/{name}" in workflow_text}
