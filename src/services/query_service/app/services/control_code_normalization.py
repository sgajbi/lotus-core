from __future__ import annotations

from typing import Any


def normalize_control_code(value: Any, *, default: str = "") -> str:
    normalized = str(value or "").strip().upper()
    return normalized or default
