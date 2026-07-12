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
