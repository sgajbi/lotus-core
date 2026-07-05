import re
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from portfolio_common.http_app_bootstrap import (
    HTTP_TRUSTED_HOSTS_ENV,
    METRICS_INTERNAL_OPEN_MODE,
    METRICS_PROTECTED_SCRAPE_MODE,
    SECURE_RESPONSE_HEADERS,
    UNMATCHED_ROUTE_TEMPLATE,
    configure_standard_http_app,
    create_standard_health_app,
    http_metric_path_template,
    normalize_trace_id,
    resolve_metrics_access_policy,
)
from starlette.requests import Request

TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def test_normalize_trace_id_accepts_valid_hex_trace_id():
    assert (
        normalize_trace_id("0123456789abcdef0123456789ABCDEF") == "0123456789abcdef0123456789abcdef"
    )


def test_normalize_trace_id_rejects_invalid_values():
    assert normalize_trace_id(None) is None
    assert normalize_trace_id("   ") is None
    assert normalize_trace_id("<not-set>") is None
    assert normalize_trace_id("trace-123") is None
    assert normalize_trace_id("0123") is None


def test_http_metric_path_template_falls_back_for_unmatched_routes():
    request = Request({"type": "http", "method": "GET", "path": "/not-found", "headers": []})

    assert http_metric_path_template(request) == UNMATCHED_ROUTE_TEMPLATE


def test_standard_http_metrics_use_route_template_for_dynamic_paths():
    app = FastAPI()

    @app.get("/portfolios/{portfolio_id}/positions/{security_id}")
    def read_position(portfolio_id: str, security_id: str):
        return {"portfolio_id": portfolio_id, "security_id": security_id}

    latency_metric = MagicMock()
    request_metric = MagicMock()

    with (
        patch("portfolio_common.http_app_bootstrap.HTTP_REQUEST_LATENCY_SECONDS", latency_metric),
        patch("portfolio_common.http_app_bootstrap.HTTP_REQUESTS_TOTAL", request_metric),
    ):
        configure_standard_http_app(
            app,
            service_name="test-service",
            service_prefix="TST",
            logger=MagicMock(),
            id_generator=lambda prefix: f"{prefix}-id",
        )

        client = TestClient(app)
        first_response = client.get("/portfolios/P1/positions/S1")
        second_response = client.get("/portfolios/P2/positions/S2")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    observed_paths = [
        call.kwargs["endpoint_template"] for call in latency_metric.labels.call_args_list
    ]
    assert observed_paths == [
        "/portfolios/{portfolio_id}/positions/{security_id}",
        "/portfolios/{portfolio_id}/positions/{security_id}",
    ]
    assert {call.kwargs["endpoint_template"] for call in request_metric.labels.call_args_list} == {
        "/portfolios/{portfolio_id}/positions/{security_id}"
    }


def test_standard_health_app_exposes_shared_observability_contract():
    latency_metric = MagicMock()
    request_metric = MagicMock()

    with (
        patch("portfolio_common.http_app_bootstrap.HTTP_REQUEST_LATENCY_SECONDS", latency_metric),
        patch("portfolio_common.http_app_bootstrap.HTTP_REQUESTS_TOTAL", request_metric),
    ):
        app = create_standard_health_app(
            title="Worker Health",
            service_name="worker_service_web",
            service_prefix="WRK",
            dependencies=(),
            logger=MagicMock(),
            id_generator=lambda prefix: f"{prefix}-id",
        )
        client = TestClient(app)
        response = client.get("/health/live")
        schema = client.get("/openapi.json").json()

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "WRK-id"
    assert response.headers["X-Request-Id"] == "REQ-id"
    trace_id = response.headers["X-Trace-Id"]
    traceparent = response.headers["traceparent"]
    assert trace_id
    assert TRACEPARENT_PATTERN.fullmatch(traceparent)
    assert traceparent.startswith(f"00-{trace_id}-")
    assert traceparent.split("-")[2] != "0000000000000001"
    assert "/metrics" in schema["paths"]
    assert schema["paths"]["/metrics"]["get"]["responses"]["200"]["content"] == {
        "text/plain": {"schema": {"type": "string"}}
    }
    assert any(
        call.kwargs
        == {
            "service": "worker_service_web",
            "method": "GET",
            "endpoint_template": "/health/live",
        }
        for call in latency_metric.labels.call_args_list
    )
    assert any(
        call.kwargs
        == {
            "service": "worker_service_web",
            "method": "GET",
            "endpoint_template": "/health/live",
            "status": "200",
        }
        for call in request_metric.labels.call_args_list
    )


def test_standard_http_app_preserves_incoming_traceparent_context():
    app = FastAPI()

    @app.get("/lineage")
    def read_lineage():
        return {"ok": True}

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
    )

    traceparent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    response = TestClient(app).get("/lineage", headers={"traceparent": traceparent})

    assert response.status_code == 200
    assert response.headers["traceparent"] == traceparent
    assert response.headers["X-Trace-Id"] == "0123456789abcdef0123456789abcdef"


def test_standard_http_app_adds_secure_response_headers():
    app = FastAPI()

    @app.get("/lineage")
    def read_lineage():
        return {"ok": True}

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
    )

    response = TestClient(app).get("/lineage")

    assert response.status_code == 200
    for header, value in SECURE_RESPONSE_HEADERS.items():
        assert response.headers[header] == value


def test_standard_http_app_cors_defaults_to_no_browser_origin_access(monkeypatch):
    monkeypatch.delenv("LOTUS_HTTP_CORS_ALLOW_ORIGINS", raising=False)
    app = FastAPI()

    @app.get("/lineage")
    def read_lineage():
        return {"ok": True}

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
    )

    response = TestClient(app).options(
        "/lineage",
        headers={
            "Origin": "https://workbench.dev.lotus",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_standard_http_app_allows_configured_cors_origin():
    app = FastAPI()

    @app.get("/lineage")
    def read_lineage():
        return {"ok": True}

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
        cors_allow_origins=("https://workbench.dev.lotus",),
    )

    response = TestClient(app).options(
        "/lineage",
        headers={
            "Origin": "https://workbench.dev.lotus",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://workbench.dev.lotus"


def test_standard_http_app_trusted_hosts_defaults_to_wildcard_for_local(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv(HTTP_TRUSTED_HOSTS_ENV, raising=False)
    app = FastAPI()

    @app.get("/lineage")
    def read_lineage():
        return {"ok": True}

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
    )

    response = TestClient(app, base_url="http://any-local-host.test").get("/lineage")

    assert response.status_code == 200
    assert app.state.lotus_trusted_hosts == ("*",)


def test_standard_http_app_enforces_configured_trusted_hosts(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    app = FastAPI()

    @app.get("/lineage")
    def read_lineage():
        return {"ok": True}

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
        trusted_hosts=("api.lotus.local",),
    )

    allowed_response = TestClient(app, base_url="http://api.lotus.local").get("/lineage")
    denied_response = TestClient(app, base_url="http://untrusted.lotus.local").get("/lineage")

    assert allowed_response.status_code == 200
    assert denied_response.status_code == 400
    for header, value in SECURE_RESPONSE_HEADERS.items():
        assert denied_response.headers[header] == value
    assert app.state.lotus_trusted_hosts == ("api.lotus.local",)


def test_standard_http_app_requires_trusted_hosts_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", raising=False)
    monkeypatch.delenv(HTTP_TRUSTED_HOSTS_ENV, raising=False)
    app = FastAPI()

    with pytest.raises(RuntimeError, match=HTTP_TRUSTED_HOSTS_ENV):
        configure_standard_http_app(
            app,
            service_name="test-service",
            service_prefix="TST",
            logger=MagicMock(),
            id_generator=lambda prefix: f"{prefix}-id",
        )


def test_standard_http_app_rejects_wildcard_trusted_host_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(HTTP_TRUSTED_HOSTS_ENV, "*")
    app = FastAPI()

    with pytest.raises(RuntimeError, match="must not include"):
        configure_standard_http_app(
            app,
            service_name="test-service",
            service_prefix="TST",
            logger=MagicMock(),
            id_generator=lambda prefix: f"{prefix}-id",
        )


def test_standard_http_app_derives_w3c_traceparent_from_trace_id_header():
    app = FastAPI()

    @app.get("/lineage")
    def read_lineage():
        return {"ok": True}

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
    )

    trace_id = "0123456789abcdef0123456789abcdef"
    response = TestClient(app).get("/lineage", headers={"X-Trace-Id": trace_id})

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] == trace_id
    traceparent = response.headers["traceparent"]
    assert TRACEPARENT_PATTERN.fullmatch(traceparent)
    assert traceparent.startswith(f"00-{trace_id}-")
    assert traceparent.split("-")[2] != "0000000000000001"


def test_metrics_access_policy_defaults_to_internal_open(monkeypatch):
    monkeypatch.delenv("LOTUS_METRICS_ACCESS_TOKEN", raising=False)

    policy = resolve_metrics_access_policy()

    assert policy.mode == METRICS_INTERNAL_OPEN_MODE
    assert policy.token is None


def test_metrics_access_policy_uses_configured_bearer_token(monkeypatch):
    monkeypatch.setenv("LOTUS_METRICS_ACCESS_TOKEN", " scrape-secret ")

    policy = resolve_metrics_access_policy()

    assert policy.mode == METRICS_PROTECTED_SCRAPE_MODE
    assert policy.token == "scrape-secret"


def test_metrics_endpoint_denies_unauthorized_scrape_when_token_configured():
    app = FastAPI()
    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
        metrics_access_token="scrape-secret",
    )
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "METRICS_ACCESS_DENIED",
        "message": "Metrics endpoint access is restricted to authorized scrapers.",
        "metrics_access_mode": METRICS_PROTECTED_SCRAPE_MODE,
    }


def test_metrics_endpoint_allows_authorized_scrape_when_token_configured():
    app = FastAPI()
    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
        metrics_access_token="scrape-secret",
    )
    client = TestClient(app)

    response = client.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})

    assert response.status_code == 200
    assert "http_requests_total{" in response.text


def test_openapi_documents_metrics_access_policy():
    app = FastAPI()
    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=MagicMock(),
        id_generator=lambda prefix: f"{prefix}-id",
        metrics_access_token="scrape-secret",
    )
    client = TestClient(app)

    metrics_operation = client.get("/openapi.json").json()["paths"]["/metrics"]["get"]

    assert metrics_operation["summary"] == "Prometheus metrics scrape endpoint"
    assert "not a public business API" in metrics_operation["description"]
    assert metrics_operation["responses"]["200"]["content"] == {
        "text/plain": {"schema": {"type": "string"}}
    }
    denied_example = metrics_operation["responses"]["403"]["content"]["application/json"]["example"]
    assert denied_example["detail"]["code"] == "METRICS_ACCESS_DENIED"
