from __future__ import annotations

from typing import Any


class ApplicationError(Exception):
    """Framework-independent application failure with source-safe details."""

    def __init__(
        self,
        *,
        reason_code: str,
        detail: Any,
        retryable: bool = False,
    ) -> None:
        self.reason_code = reason_code
        self.detail = detail
        self.retryable = retryable
        super().__init__(str(detail))


class ValidationRejected(ApplicationError):
    """Application input was rejected by use-case validation."""


class UnsupportedOperation(ApplicationError):
    """Requested capability is unsupported by the application use case."""
