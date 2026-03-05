import pytest
from fastapi import HTTPException, status

from src.services.query_service.app.routers.legacy_gone import (
    legacy_gone_response,
    raise_legacy_endpoint_gone,
)


def test_legacy_gone_response_contains_expected_payload() -> None:
    payload = legacy_gone_response(
        capability="performance",
        target_service="lotus-performance",
        target_endpoint="/v1/performance",
    )
    detail = payload["content"]["application/json"]["example"]["detail"]

    assert payload["description"].startswith("Endpoint has been removed")
    assert detail["code"] == "LOTUS_CORE_LEGACY_ENDPOINT_REMOVED"
    assert detail["capability"] == "performance"
    assert detail["target_service"] == "lotus-performance"
    assert detail["target_endpoint"] == "/v1/performance"


def test_raise_legacy_endpoint_gone_raises_http_410() -> None:
    with pytest.raises(HTTPException) as exc_info:
        raise_legacy_endpoint_gone(
            capability="review",
            target_service="lotus-report",
            target_endpoint="/reports/portfolio/review",
        )

    assert exc_info.value.status_code == status.HTTP_410_GONE
    detail = exc_info.value.detail
    assert detail["code"] == "LOTUS_CORE_LEGACY_ENDPOINT_REMOVED"
    assert detail["target_service"] == "lotus-report"
