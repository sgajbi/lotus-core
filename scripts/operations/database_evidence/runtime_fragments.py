"""Optional test-to-command fragment publication boundary."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .contract import HotPathPlanResult, write_hot_path_plan_fragment

FRAGMENT_DIRECTORY_ENV = "LOTUS_DATABASE_HOT_PATH_FRAGMENT_DIR"


def publish_requested_fragments(results: Iterable[HotPathPlanResult]) -> None:
    """Publish results only when the repository-native command requests them."""

    raw_directory = os.environ.get(FRAGMENT_DIRECTORY_ENV)
    if raw_directory is None:
        return
    directory = Path(raw_directory)
    for result in results:
        write_hot_path_plan_fragment(directory, result)
