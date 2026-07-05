from __future__ import annotations

from typing import Any, Protocol

from fastapi import HTTPException


class CommandHttpError(Protocol):
    status_code: int
    detail: dict[str, Any]


def command_error_to_http(exc: CommandHttpError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)
