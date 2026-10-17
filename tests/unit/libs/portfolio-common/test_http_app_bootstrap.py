import asyncio
import io
import json
import logging
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from portfolio_common.enterprise_readiness import EnterpriseReadinessRuntime
from portfolio_common.enterprise_request_context import request_correlation_id
from portfolio_common.http_app_bootstrap import (
    HTTP_TRUSTED_HOSTS_ENV,
    METRICS_INTERNAL_OPEN_MODE,
    METRICS_PROTECTED_SCRAPE_MODE,
    SECURE_RESPONSE_HEADERS,
    UNMATCHED_ROUTE_TEMPLATE,
    MetricsAccessPolicy,
    configure_cors_policy,
    configure_metrics_access_policy,
    configure_secure_response_headers,
    configure_standard_http_app,
    configure_standard_openapi,
    configure_trusted_host_policy,
    create_standard_health_app,
    http_metric_path_template,
    normalize_trace_id,
    resolve_metrics_access_policy,
)
from portfolio_common.logging_utils import (
    CorrelationIdFilter,
    RedactingJsonFormatter,
    correlation_id_var,
    request_id_var,
    trace_id_var,
    traceparent_var,
)
from starlette.requests import Request

TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


@pytest.mark.parametrize(
    ("headers", "response_id", "context_id", "expected"),
    [
        (
            {"X-Correlation-Id": " valid-primary ", "X-Correlation-ID": "secondary"},
            "response",
            "context",
            "valid-primary",
        ),
        ({"X-Correlation-ID": "secondary"}, "response", "context", "secondary"),
        (
            {"X-Correlation-Id": "<NOT-SET>", "X-Correlation-ID": "secondary"},
            "response",
            "context",
            "secondary",
        ),
        ({"X-Correlation-Id": "<not-set>"}, "response", "context", "response"),
        ({"X-Correlation-Id": " <NoT-SeT> "}, " <NOT-SET> ", "context", "context"),
        ({"X-Correlation-Id": "   "}, " ", "context", "context"),
        ({}, None, "context", "context"),
        ({}, None, "<not-set>", None),
        ({"X-Correlation-Id": "c" * 128}, "response", "context", "c" * 128),
        ({"X-Correlation-Id": "c" * 129}, "response", "context", None),
    ],
)
def test_audit_correlation_falls_through_unset_candidates_with_valid_priority(
    headers, response_id, context_id, expected
):
    token = correlation_id_var.set(context_id)
    try:
        assert request_correlation_id(headers, response_id) == expected
    finally:
        correlation_id_var.reset(token)


@pytest.fixture
def formatted_http_logs(monkeypatch):
    stream = io.StringIO()
    logger = logging.Logger("http-lineage-contract", level=logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.addFilter(CorrelationIdFilter())
    handler.setFormatter(RedactingJsonFormatter("%(message)s"))
    logger.addHandler(handler)
    latency_metric, request_metric = MagicMock(), MagicMock()
    monkeypatch.setattr(
        "portfolio_common.http_app_bootstrap.HTTP_REQUEST_LATENCY_SECONDS", latency_metric
    )
    monkeypatch.setattr("portfolio_common.http_app_bootstrap.HTTP_REQUESTS_TOTAL", request_metric)
    yield logger, stream, latency_metric, request_metric
    handler.close()


@pytest.mark.parametrize("identity", ["explicit", "generated", "invalid"])
@pytest.mark.parametrize("outcome", ["success", "denied", "foreign", "validation", "error"])
def test_formatted_http_completion_joins_normalized_response_identity(
    formatted_http_logs, identity, outcome
):
    logger, stream, latency_metric, request_metric = formatted_http_logs
    app = FastAPI()

    @app.get("/portfolios/{portfolio_id}")
    async def read_portfolio(portfolio_id: int):
        if outcome == "error":
            raise RuntimeError("source unavailable")
        if outcome in {"denied", "foreign"}:
            raise HTTPException(status_code={"denied": 401, "foreign": 404}[outcome])
        return {"portfolio_id": portfolio_id}

    configure_standard_http_app(
        app, service_name="lineage-test", service_prefix="TST", logger=logger
    )
    headers = {}
    if identity == "explicit":
        headers = {
            "X-Correlation-Id": "  supplied-correlation  ",
            "X-Request-Id": "  supplied-request  ",
            "traceparent": "00-1234567890ABCDEF1234567890ABCDEF-1234567890ABCDEF-01",
            "X-Trace-Id": "abcdefabcdefabcdefabcdefabcdefab",
        }
    elif identity == "invalid":
        headers = {
            "X-Correlation-Id": " <NOT-SET> ",
            "X-Request-Id": "  ",
            "traceparent": "00-" + "0" * 32 + "-1234567890abcdef-01",
            "X-Trace-Id": "invalid-trace",
        }
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/portfolios/private-identifier" if outcome == "validation" else "/portfolios/123",
            headers=headers,
        )
    expected_status = {
        "success": 200,
        "denied": 401,
        "foreign": 404,
        "validation": 422,
        "error": 500,
    }[outcome]
    assert response.status_code == expected_status
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    completions = [record for record in records if record["message"] == "http_request_completed"]
    assert len(completions) == 1
    completion = completions[0]
    for field, header in (
        ("correlation_id", "X-Correlation-Id"),
        ("request_id", "X-Request-Id"),
        ("trace_id", "X-Trace-Id"),
        ("traceparent", "traceparent"),
    ):
        assert completion[field] == response.headers[header]
        assert completion[field] and completion[field] != "<not-set>"
    assert TRACEPARENT_PATTERN.fullmatch(completion["traceparent"])
    assert completion["traceparent"].split("-")[1] == completion["trace_id"]
    if identity == "explicit":
        assert completion["correlation_id"] == "supplied-correlation"
        assert completion["request_id"] == "supplied-request"
        assert completion["trace_id"] == "1234567890abcdef1234567890abcdef"
    assert completion["route_template"] == "/portfolios/{portfolio_id}"
    assert completion["status_code"] == expected_status
    labels = {
        "service": "lineage-test",
        "method": "GET",
        "endpoint_template": "/portfolios/{portfolio_id}",
    }
    latency_metric.labels.assert_called_once_with(**labels)
    latency_metric.labels.return_value.observe.assert_called_once()
    request_metric.labels.assert_called_once_with(status=str(expected_status), **labels)
    request_metric.labels.return_value.inc.assert_called_once_with()
    assert "private-identifier" not in stream.getvalue()
    assert len([r for r in records if r["message"] == "http_request_unhandled_exception"]) == (
        1 if outcome == "error" else 0
    )
    for header, value in SECURE_RESPONSE_HEADERS.items():
        assert response.headers[header] == value


@pytest.mark.asyncio
async def test_formatted_http_completion_concurrency_and_context_reset(formatted_http_logs):
    logger, stream, latency_metric, request_metric = formatted_http_logs
    app = FastAPI()
    entered = 0
    both_entered = asyncio.Event()
    audit_runtime = EnterpriseReadinessRuntime(
        service_name="lineage-concurrency",
        load_settings=lambda: SimpleNamespace(enterprise_policy_version="test-policy"),
        env_bool=lambda name, default: default,
        env_int=lambda name, default: default,
        logger=logger,
    )

    @app.get("/concurrent")
    async def concurrent_request(request: Request):
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await asyncio.wait_for(both_entered.wait(), timeout=5)
        audit_runtime.emit_audit_event(
            action="GET /concurrent",
            actor_id="test-actor",
            tenant_id="test-tenant",
            role="test-role",
            correlation_id=request_correlation_id(request.headers),
            metadata={},
        )
        return {}

    configure_standard_http_app(
        app, service_name="lineage-concurrency", service_prefix="TST", logger=logger
    )
    variables = (correlation_id_var, request_id_var, trace_id_var, traceparent_var)
    before = tuple(variable.get() for variable in variables)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            *(
                client.get(
                    "/concurrent",
                    headers={
                        "X-Correlation-Id": "concurrent-1" if index == 1 else " <NOT-SET> ",
                        "X-Request-Id": f"request-{index}",
                        "traceparent": f"00-{index:032x}-{index:016x}-01",
                    },
                )
                for index in (1, 2)
            )
        )
        generated = await client.get("/concurrent", headers={"X-Correlation-Id": " <NoT-SeT> "})
    assert tuple(variable.get() for variable in variables) == before
    logger.info("outside_request")
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    completions = [r for r in records if r["message"] == "http_request_completed"]
    assert len(completions) == 3
    assert request_metric.labels.return_value.inc.call_count == 3
    assert latency_metric.labels.return_value.observe.call_count == 3
    assert len({r["request_id"] for r in completions}) == 3
    assert len({r["correlation_id"] for r in completions}) == 3
    audits = [r for r in records if r["message"] == "enterprise_audit_event"]
    assert len(audits) == 3
    for response in [*responses, generated]:
        assert response.status_code == 200
        matching = [r for r in completions if r["request_id"] == response.headers["X-Request-Id"]]
        assert len(matching) == 1
        matching_audits = [r for r in audits if r["request_id"] == response.headers["X-Request-Id"]]
        assert len(matching_audits) == 1
        assert matching_audits[0]["audit"]["correlation_id"] == matching[0]["correlation_id"]
        assert matching_audits[0]["correlation_id"] == matching[0]["correlation_id"]
        for field, header in (
            ("correlation_id", "X-Correlation-Id"),
            ("trace_id", "X-Trace-Id"),
            ("traceparent", "traceparent"),
        ):
            assert matching[0][field] == response.headers[header]
    assert generated.headers["X-Correlation-Id"] not in {"concurrent-1", "concurrent-2"}
    assert records[-1]["message"] == "outside_request"
    assert all(
        records[-1][field] is None
        for field in ("correlation_id", "request_id", "trace_id", "traceparent")
    )


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


def test_standard_http_logs_never_emit_dynamic_path_identifiers():
    app = FastAPI()
    logger = MagicMock()
    sensitive_portfolio_id = "PORT-CUSTOMER-SECRET"
    sensitive_transaction_id = "TXN-CUSTOMER-SECRET"

    @app.get("/portfolios/{portfolio_id}/transactions/{transaction_id}")
    def read_transaction(portfolio_id: str, transaction_id: str):
        return {"portfolio_id": portfolio_id, "transaction_id": transaction_id}

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=logger,
        id_generator=lambda prefix: f"{prefix}-id",
    )

    response = TestClient(app).get(
        f"/portfolios/{sensitive_portfolio_id}/transactions/{sensitive_transaction_id}"
    )

    assert response.status_code == 200
    completion_call = next(
        call for call in logger.info.call_args_list if call.args == ("http_request_completed",)
    )
    completion_fields = completion_call.kwargs["extra"]
    assert set(completion_fields) == {"method", "route_template", "status_code", "duration_ms"}
    assert completion_fields["method"] == "GET"
    assert completion_fields["route_template"] == (
        "/portfolios/{portfolio_id}/transactions/{transaction_id}"
    )
    assert completion_fields["status_code"] == 200
    assert isinstance(completion_fields["duration_ms"], float)
    assert completion_fields["duration_ms"] >= 0
    rendered_call = repr(completion_call)
    assert sensitive_portfolio_id not in rendered_call
    assert sensitive_transaction_id not in rendered_call


def test_standard_http_error_logs_use_route_template_without_dynamic_identifiers():
    app = FastAPI()
    logger = MagicMock()
    sensitive_transaction_id = "TXN-CUSTOMER-SECRET"

    @app.get("/transactions/{transaction_id}")
    def fail_transaction(transaction_id: str):
        raise RuntimeError("source unavailable")

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=logger,
        id_generator=lambda prefix: f"{prefix}-id",
    )

    response = TestClient(app, raise_server_exceptions=False).get(
        f"/transactions/{sensitive_transaction_id}"
    )

    assert response.status_code == 500
    failure_call = next(
        call
        for call in logger.critical.call_args_list
        if call.args == ("http_request_unhandled_exception",)
    )
    assert failure_call.kwargs["extra"] == {
        "correlation_id": "TST-id",
        "method": "GET",
        "route_template": "/transactions/{transaction_id}",
    }
    assert sensitive_transaction_id not in repr(failure_call)


def test_standard_http_fails_safe_when_lineage_initialization_raises():
    app = FastAPI()
    logger = MagicMock()
    id_generation_attempts = 0

    @app.get("/lineage")
    def read_lineage():
        return {"ok": True}

    def fail_first_id_generation(prefix: str) -> str:
        nonlocal id_generation_attempts
        id_generation_attempts += 1
        if id_generation_attempts == 1:
            raise RuntimeError("lineage id generator unavailable")
        return f"{prefix}-fallback"

    configure_standard_http_app(
        app,
        service_name="test-service",
        service_prefix="TST",
        logger=logger,
        id_generator=fail_first_id_generation,
    )

    response = TestClient(app, raise_server_exceptions=False).get(
        "/lineage",
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": "Internal Server Error",
        "message": "An unexpected error occurred. Please contact support.",
        "correlation_id": "TST-fallback",
    }
    assert response.headers["X-Correlation-ID"] == "TST-fallback"
    assert response.headers["X-Request-Id"] == "REQ-fallback"
    assert TRACEPARENT_PATTERN.fullmatch(response.headers["traceparent"])
    for header, value in SECURE_RESPONSE_HEADERS.items():
        assert response.headers[header] == value
    failure_call = next(
        call
        for call in logger.critical.call_args_list
        if call.args == ("http_request_unhandled_exception",)
    )
    assert failure_call.kwargs["extra"] == {
        "correlation_id": "TST-fallback",
        "method": "GET",
        "route_template": UNMATCHED_ROUTE_TEMPLATE,
    }


def test_shared_http_security_policy_configuration_is_idempotent(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    app = FastAPI()
    metrics_policy = MetricsAccessPolicy(mode=METRICS_INTERNAL_OPEN_MODE)

    configure_metrics_access_policy(app, metrics_access_policy=metrics_policy)
    configure_metrics_access_policy(app, metrics_access_policy=metrics_policy)
    assert configure_cors_policy(app, cors_allow_origins=(" https://workbench.lotus ",)) == (
        "https://workbench.lotus",
    )
    assert configure_cors_policy(app, cors_allow_origins=("https://ignored.lotus",)) == (
        "https://workbench.lotus",
    )
    assert configure_trusted_host_policy(
        app,
        service_name="test-service",
        trusted_hosts=(" api.lotus.local ",),
    ) == ("api.lotus.local",)
    assert configure_trusted_host_policy(
        app,
        service_name="test-service",
        trusted_hosts=("ignored.lotus.local",),
    ) == ("api.lotus.local",)
    configure_secure_response_headers(app)
    middleware_count = len(app.user_middleware)
    configure_secure_response_headers(app)

    assert len(app.user_middleware) == middleware_count


def test_metrics_endpoint_fails_closed_for_inconsistent_protected_policy():
    app = FastAPI()
    configure_metrics_access_policy(
        app,
        metrics_access_policy=MetricsAccessPolicy(
            mode=METRICS_PROTECTED_SCRAPE_MODE,
            token=None,
        ),
    )

    response = TestClient(app).get("/metrics")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "METRICS_ACCESS_DENIED"


def test_standard_openapi_supports_apps_without_metrics_route():
    app = FastAPI()

    @app.get("/business")
    def read_business_state():
        return {"ok": True}

    configure_standard_openapi(app, service_name="test-service")

    first_schema = app.openapi()
    second_schema = app.openapi()

    assert first_schema is second_schema
    assert "/business" in first_schema["paths"]
    assert "/metrics" not in first_schema["paths"]


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
        metrics_response = client.get("/metrics")
        schema = client.get("/openapi.json").json()

    assert response.status_code == 200
    assert metrics_response.status_code == 200
    assert response.json()["runtime"]["service_name"] == "worker_service_web"
    assert response.json()["runtime"]["app_version"] == "1.0.0"
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
    response = TestClient(app).get(
        "/lineage",
        headers={"traceparent": traceparent, "X-Request-Id": "REQ-client"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "REQ-client"
    assert response.headers["traceparent"] == traceparent
    assert response.headers["X-Trace-Id"] == "0123456789abcdef0123456789abcdef"


def test_standard_http_app_replaces_malformed_traceparent_context():
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

    response = TestClient(app).get(
        "/lineage",
        headers={"traceparent": "00-not-a-valid-traceparent"},
    )

    assert response.status_code == 200
    assert TRACEPARENT_PATTERN.fullmatch(response.headers["traceparent"])
    assert response.headers["traceparent"] != "00-not-a-valid-traceparent"
    assert response.headers["traceparent"].startswith(f"00-{response.headers['X-Trace-Id']}-")


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

    # A scrape cannot expose its own counter increment until the response finishes.
    served = client.get("/version")
    assert served.status_code == 200
    response = client.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})

    assert response.status_code == 200
    assert any(
        line.startswith("http_requests_total{")
        and 'service="test-service"' in line
        and 'method="GET"' in line
        and 'endpoint_template="/version"' in line
        and 'status="200"' in line
        for line in response.text.splitlines()
    )


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
