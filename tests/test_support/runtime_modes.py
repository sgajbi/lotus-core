from __future__ import annotations

from collections.abc import Iterable


def classify_runtime_mode(nodeid: str, marker_names: Iterable[str] = ()) -> str | None:
    normalized = nodeid.replace("\\", "/").lower()
    normalized_markers = {name.lower() for name in marker_names}

    if "tests/e2e/" in normalized:
        return "live_worker"
    if "tests/integration/" in normalized or "integration_db" in normalized_markers:
        return "db_direct"
    return None


def detect_runtime_modes(
    collected_items: Iterable[tuple[str, Iterable[str]]],
) -> dict[str, list[str]]:
    modes: dict[str, list[str]] = {}
    for nodeid, marker_names in collected_items:
        runtime_mode = classify_runtime_mode(nodeid, marker_names)
        if runtime_mode is None:
            continue
        modes.setdefault(runtime_mode, []).append(nodeid)
    return modes

