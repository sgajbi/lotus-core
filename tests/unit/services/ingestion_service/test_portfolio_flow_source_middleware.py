"""Actual middleware verifies signed identity/capability before producer grant admission."""

from time import time

import pytest
from fastapi import Request
from fastapi.responses import Response
from portfolio_common.domain.portfolio_source_observations import (
    ObservationConflict,
    ObservationFamily,
)
from portfolio_common.enterprise_readiness import (
    _enterprise_auth_context_signature,
    _normalize_headers,
)
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAuthority,
)

from src.services.ingestion_service.app import enterprise_readiness as enterprise

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "endpoint,capability",
    [
        (
            "/ingest/portfolio-flow-event-observations",
            "ingestion.portfolio_flow_event_observations.write",
        ),
        ("/ingest/portfolio-flow-source-cuts", "ingestion.portfolio_flow_source_cuts.write"),
    ],
)
@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("valid", 200),
        ("missing-capability", 403),
        ("wrong-capability", 403),
        ("foreign-tenant", 403),
        ("foreign-producer", 403),
        ("unsigned-identity", 403),
    ],
)
async def test_actual_middleware_and_grant_refuse_scope_spoofing(
    monkeypatch, endpoint, capability, scenario, expected
):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "unit-flow-key")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "unit-flow-signature-secret")
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)
    monkeypatch.setattr(enterprise, "create_runtime_security_audit_store", lambda **kwargs: None)
    monkeypatch.setattr(enterprise, "emit_audit_event", lambda **kwargs: None)
    headers = {
        "X-Actor-Id": "synthetic-actor",
        "X-Tenant-Id": "tenant-synthetic",
        "X-Role": "ops",
        "X-Correlation-Id": "synthetic-correlation",
        "X-Service-Identity": "producer-synthetic",
        "X-Capabilities": capability,
        "X-Enterprise-Auth-Key-Id": "unit-flow-key",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
    }
    if scenario == "missing-capability":
        headers["X-Capabilities"] = ""
    if scenario == "wrong-capability":
        headers["X-Capabilities"] = "ingestion.portfolio_cash_availability_observations.write"
    if scenario == "foreign-tenant":
        headers["X-Tenant-Id"] = "foreign-tenant"
    if scenario == "foreign-producer":
        headers["X-Service-Identity"] = "foreign-producer"
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers),
        "unit-flow-signature-secret",
    )
    if scenario == "unsigned-identity":
        headers["X-Service-Identity"] = "spoofed-after-signature"
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": endpoint,
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]
            + [(b"content-length", b"0")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    grant = ProducerSubmissionGrant(
        "tenant-synthetic",
        "portfolio-synthetic",
        "producer-synthetic",
        ObservationFamily.FLOW_EVENT,
    )
    authority = UnqualifiedProducerAuthority((grant,))
    admitted = []

    async def next_handler(http):
        try:
            admission = authority.admit(http.state.tenant_context, grant)
        except ObservationConflict:
            return Response(status_code=403)
        admitted.append(admission)
        assert http.state.tenant_context.identity_verified
        return Response(status_code=200)

    result = await enterprise.build_enterprise_audit_middleware()(request, next_handler)
    assert result.status_code == expected
    assert bool(admitted) == (scenario == "valid")
