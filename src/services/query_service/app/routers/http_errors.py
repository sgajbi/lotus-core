from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status


def lookup_error_to_http(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def value_error_to_http(
    exc: ValueError,
    *,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> HTTPException:
    return HTTPException(status_code=status_code, detail=str(exc))


def value_error_as_resolution_http(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status_code = (
        status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=status_code, detail=detail)


def raise_value_error_as_resolution_http(exc: ValueError) -> NoReturn:
    """Map service resolution errors to the query-service read API contract."""
    raise value_error_as_resolution_http(exc) from exc
