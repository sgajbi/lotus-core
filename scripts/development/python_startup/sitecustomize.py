"""Activate the repository-owned first-party import fence in child interpreters."""

from __future__ import annotations

import os
import sys
from pathlib import Path

development_root = Path(__file__).resolve().parent.parent
development_root_added = str(development_root) not in sys.path
if development_root_added:
    sys.path.insert(0, str(development_root))

from repository_import_guard import activate_repository_import_guard  # noqa: E402

if development_root_added:
    sys.path.remove(str(development_root))

repository_root = os.environ.get("LOTUS_REPOSITORY_ROOT")
if repository_root:
    activate_repository_import_guard(Path(repository_root))
