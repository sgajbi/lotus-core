from __future__ import annotations

from typing import Any


def normalize_security_id(value: Any) -> str:
    return str(value or "").strip()
