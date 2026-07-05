from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI

from portfolio_common.http_app_bootstrap import SECURE_RESPONSE_HEADERS

TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def _ensure_contract_exception_route(app: FastAPI, path: str) -> None:
    if any(getattr(route, "path", None) == path for route in app.routes):
        return

    @app.get(path)
    async def _raise_contract_error() -> None:
        raise RuntimeError("middleware contract failure probe")


async def assert_standard_http_middleware_contract(
    *,
    app: FastAPI,
    service_name: str,
    correlation_id: str,
) -> None:
    latency_metric = MagicMock()
    request_metric = MagicMock()
    exception_path = f"/__middleware_contract__/{service_name}/raise"
    _ensure_contract_exception_route(app, exception_path)

    with (
        patch("portfolio_common.http_app_bootstrap.HTTP_REQUEST_LATENCY_SECONDS", latency_metric),
        patch("portfolio_common.http_app_bootstrap.HTTP_REQUESTS_TOTAL", request_metric),
    ):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/version",
                headers={
                    "X-Correlation-ID": correlation_id,
                    "X-Request-Id": f"{correlation_id}-request",
                },
            )
            error_response = await client.get(
                exception_path,
                headers={"X-Correlation-ID": correlation_id},
            )

    assert response.status_code == 200
    assert response.json()["service_name"] == service_name
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert response.headers["X-Correlation-Id"] == correlation_id
    assert response.headers["X-Request-Id"] == f"{correlation_id}-request"
    assert TRACEPARENT_PATTERN.fullmatch(response.headers["traceparent"])
    assert response.headers["traceparent"].startswith(f"00-{response.headers['X-Trace-Id']}-")
    for header, value in SECURE_RESPONSE_HEADERS.items():
        assert response.headers[header] == value

    assert error_response.status_code == 500
    assert error_response.headers["X-Correlation-ID"] == correlation_id
    assert error_response.json() == {
        "error": "Internal Server Error",
        "message": "An unexpected error occurred. Please contact support.",
        "correlation_id": correlation_id,
    }
    for header, value in SECURE_RESPONSE_HEADERS.items():
        assert error_response.headers[header] == value

    assert any(
        call.kwargs
        == {
            "service": service_name,
            "method": "GET",
            "endpoint_template": "/version",
        }
        for call in latency_metric.labels.call_args_list
    )
    assert any(
        call.kwargs
        == {
            "service": service_name,
            "method": "GET",
            "endpoint_template": exception_path,
        }
        for call in latency_metric.labels.call_args_list
    )
    assert any(
        call.kwargs
        == {
            "service": service_name,
            "method": "GET",
            "endpoint_template": "/version",
            "status": "200",
        }
        for call in request_metric.labels.call_args_list
    )
    assert any(
        call.kwargs
        == {
            "service": service_name,
            "method": "GET",
            "endpoint_template": exception_path,
            "status": "500",
        }
        for call in request_metric.labels.call_args_list
    )
