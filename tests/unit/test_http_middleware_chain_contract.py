import json
import logging

import httpx
import pytest
from fastapi import FastAPI
from portfolio_common.logging_utils import CorrelationIdFilter, RedactingJsonFormatter

from src.services.calculators.position_valuation_calculator.app.web import (
    app as position_valuation_calculator_app,
)
from src.services.event_replay_service.app.main import app as event_replay_service_app
from src.services.financial_reconciliation_service.app.main import (
    app as financial_reconciliation_service_app,
)
from src.services.ingestion_service.app.main import app as ingestion_service_app
from src.services.persistence_service.app.web import app as persistence_service_app
from src.services.portfolio_derived_state_service.app.web import (
    app as portfolio_derived_state_service_app,
)
from src.services.portfolio_transaction_processing_service.app.web import (
    app as portfolio_transaction_processing_service_app,
)
from src.services.query_control_plane_service.app.main import (
    app as query_control_plane_service_app,
)
from src.services.query_service.app.main import app as query_service_app
from src.services.valuation_orchestrator_service.app.web import (
    app as valuation_orchestrator_service_app,
)
from tests.test_support.http_middleware_contract import (
    assert_standard_http_middleware_contract,
)

SERVICE_APPS: tuple[tuple[str, FastAPI], ...] = (
    (
        "portfolio_transaction_processing_service_web",
        portfolio_transaction_processing_service_app,
    ),
    ("position_valuation_calculator_service_web", position_valuation_calculator_app),
    ("event_replay_service", event_replay_service_app),
    ("financial_reconciliation_service", financial_reconciliation_service_app),
    ("ingestion_service", ingestion_service_app),
    ("persistence_service_web", persistence_service_app),
    ("portfolio_derived_state_service_web", portfolio_derived_state_service_app),
    ("query_control_plane_service", query_control_plane_service_app),
    ("query_service", query_service_app),
    ("valuation_orchestrator_service_web", valuation_orchestrator_service_app),
)


@pytest.fixture(autouse=True)
def assert_shared_capture_handler_isolation(caplog):
    original_formatter = caplog.handler.formatter
    original_filters = tuple(caplog.handler.filters)
    yield
    assert caplog.handler.formatter is original_formatter
    assert tuple(caplog.handler.filters) == original_filters
    subsequent_record = logging.LogRecord(
        "formatter-isolation", logging.WARNING, __file__, 0, "subsequent log consumer", (), None
    )
    caplog.handler.handle(subsequent_record)
    formatter = original_formatter or logging.Formatter()
    assert caplog.text.endswith(f"{formatter.format(subsequent_record)}\n")


@pytest.mark.asyncio
@pytest.mark.parametrize(("service_name", "app"), SERVICE_APPS)
async def test_service_app_entrypoint_uses_standard_http_middleware_chain(
    service_name: str,
    app: FastAPI,
    caplog,
) -> None:
    caplog.set_level(logging.INFO)
    original_formatter = caplog.handler.formatter
    lineage_filter = CorrelationIdFilter()
    caplog.handler.addFilter(lineage_filter)
    caplog.handler.setFormatter(RedactingJsonFormatter("%(message)s"))
    try:
        await assert_standard_http_middleware_contract(
            app=app,
            service_name=service_name,
            correlation_id=f"{service_name}-corr",
        )
    finally:
        caplog.handler.removeFilter(lineage_filter)
        caplog.handler.setFormatter(original_formatter)
    records = [json.loads(line) for line in caplog.text.splitlines()]
    completions = [r for r in records if r["message"] == "http_request_completed"]
    assert len(completions) == 2
    assert {r["status_code"] for r in completions} == {200, 500}
    for record in completions:
        assert record["correlation_id"] == f"{service_name}-corr"
        assert record["request_id"]
        assert record["traceparent"].split("-")[1] == record["trace_id"]
    success = next(r for r in completions if r["status_code"] == 200)
    assert success["request_id"] == f"{service_name}-corr-request"
    exception = next(r for r in records if r["message"] == "http_request_unhandled_exception")
    failure = next(r for r in completions if r["status_code"] == 500)
    for field in ("correlation_id", "request_id", "trace_id", "traceparent"):
        assert failure[field] == exception[field]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity", ["explicit", "generated", "sentinel", "mixed-sentinel", "blank"]
)
@pytest.mark.parametrize("outcome", ["missing-tenant", "denied", "foreign"])
async def test_registered_query_refusals_have_joinable_completion_json(
    caplog, monkeypatch, identity, outcome
):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true" if outcome == "denied" else "false")
    caplog.set_level(logging.INFO)
    original_formatter = caplog.handler.formatter
    lineage_filter = CorrelationIdFilter()
    caplog.handler.addFilter(lineage_filter)
    caplog.handler.setFormatter(RedactingJsonFormatter("%(message)s"))
    headers = {}
    if outcome != "missing-tenant":
        headers["X-Tenant-Id"] = "tenant-test"
    if identity == "explicit":
        headers.update(
            {
                "X-Correlation-Id": "query-refusal",
                "X-Request-Id": "query-refusal-request",
                "traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01",
            }
        )
    elif identity in {"sentinel", "mixed-sentinel", "blank"}:
        headers["X-Correlation-Id"] = {
            "sentinel": "<not-set>",
            "mixed-sentinel": "  <NoT-SeT>  ",
            "blank": "   ",
        }[identity]
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(query_service_app), base_url="http://test"
        ) as client:
            response = await client.get("/__lineage_unmatched__", headers=headers)
    finally:
        caplog.handler.removeFilter(lineage_filter)
        caplog.handler.setFormatter(original_formatter)
    assert response.status_code == {"missing-tenant": 401, "denied": 403, "foreign": 404}[outcome]
    records = [json.loads(line) for line in caplog.text.splitlines()]
    completions = [r for r in records if r["message"] == "http_request_completed"]
    assert len(completions) == 1
    completion = completions[0]
    assert completion["route_template"] == "<unmatched>"
    for field, header in (
        ("correlation_id", "X-Correlation-Id"),
        ("request_id", "X-Request-Id"),
        ("trace_id", "X-Trace-Id"),
        ("traceparent", "traceparent"),
    ):
        assert completion[field] == response.headers[header]
        assert completion[field]
    audit_records = [r for r in records if r["message"] == "enterprise_audit_event"]
    if outcome == "denied":
        assert len(audit_records) == 1
        assert audit_records[0]["audit"]["correlation_id"] == completion["correlation_id"]
        assert audit_records[0]["correlation_id"] == completion["correlation_id"]
