import pytest
from fastapi import HTTPException, status

from src.services.query_service.app.routers.http_errors import (
    lookup_error_to_http,
    raise_value_error_as_resolution_http,
    value_error_to_http,
)


def test_lookup_error_to_http_maps_to_404() -> None:
    exc = lookup_error_to_http(LookupError("missing portfolio"))

    assert exc.status_code == status.HTTP_404_NOT_FOUND
    assert exc.detail == "missing portfolio"


def test_value_error_to_http_maps_to_400_by_default() -> None:
    exc = value_error_to_http(ValueError("invalid window"))

    assert exc.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.detail == "invalid window"


def test_resolution_value_error_maps_not_found_to_404() -> None:
    with pytest.raises(HTTPException) as exc_info:
        raise_value_error_as_resolution_http(ValueError("upstream not found"))

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "upstream not found"


def test_resolution_value_error_maps_other_errors_to_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        raise_value_error_as_resolution_http(ValueError("No business date is available."))

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "No business date is available."
