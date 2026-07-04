from __future__ import annotations

from typing import Any


class ReplayCommandError(Exception):
    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(str(detail.get("message", detail.get("code", "replay command failed"))))
        self.status_code = status_code
        self.detail = detail
