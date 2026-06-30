from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InfrastructureAuditWriteFailed(RuntimeError):
    message: str
    reason_code: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)
