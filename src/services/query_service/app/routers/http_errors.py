from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status

from ..application.collection_window_policy import CollectionWindowValidationError


def lookup_error_to_http(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def value_error_to_http(
    exc: ValueError,
    *,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> HTTPException:
    return HTTPException(status_code=status_code, detail=str(exc))


def collection_window_error_to_http(exc: CollectionWindowValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": exc.code,
            "message": str(exc),
            "source_product": exc.source_product,
            "start_date": exc.start_date.isoformat() if exc.start_date else None,
            "end_date": exc.end_date.isoformat() if exc.end_date else None,
            "max_window_days": exc.max_window_days,
        },
    )


def value_error_as_resolution_http(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status_code = (
        status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=status_code, detail=detail)


def raise_value_error_as_resolution_http(exc: ValueError) -> NoReturn:
    """Map service resolution errors to the query-service read API contract."""
    raise value_error_as_resolution_http(exc) from exc
