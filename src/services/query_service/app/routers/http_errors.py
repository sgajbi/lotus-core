from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status


def raise_value_error_as_resolution_http(exc: ValueError) -> NoReturn:
    """Map service resolution errors to the query-service read API contract."""
    detail = str(exc)
    status_code = (
        status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(status_code=status_code, detail=detail)
