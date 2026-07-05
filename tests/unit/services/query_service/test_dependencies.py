import pytest
from fastapi import HTTPException

from src.services.query_service.app.dependencies import pagination_params, sorting_params


def test_pagination_params_default_values():
    result = pagination_params(skip=0, limit=100)
    assert result == {"skip": 0, "limit": 100}


def test_pagination_params_custom_values():
    result = pagination_params(skip=25, limit=250)
    assert result == {"skip": 25, "limit": 250}


def test_sorting_params_default_values():
    result = sorting_params(sort_by=None, sort_order="desc")
    assert result == {"sort_by": None, "sort_order": "desc"}


def test_sorting_params_custom_values():
    result = sorting_params(sort_by="transaction_date", sort_order="asc")
    assert result == {"sort_by": "transaction_date", "sort_order": "asc"}


def test_sorting_params_rejects_invalid_sort_field():
    with pytest.raises(HTTPException) as exc_info:
        sorting_params(sort_by="settlement_currency", sort_order="asc")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_TRANSACTION_SORT_PARAMETER"
    assert exc_info.value.detail["field"] == "sort_by"
    assert "transaction_date" in exc_info.value.detail["allowed_values"]


def test_sorting_params_rejects_invalid_sort_order():
    with pytest.raises(HTTPException) as exc_info:
        sorting_params(sort_by="transaction_date", sort_order="ascending")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_TRANSACTION_SORT_PARAMETER"
    assert exc_info.value.detail["field"] == "sort_order"
    assert exc_info.value.detail["allowed_values"] == ["asc", "desc"]
