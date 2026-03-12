import pytest
from fastapi import Request
from fastapi.responses import Response
from portfolio_common.logging_utils import correlation_id_var

from src.services.query_control_plane_service.app.enterprise_readiness import (
    build_enterprise_audit_middleware,
    emit_audit_event,
)


@pytest.mark.asyncio
async def test_control_plane_enterprise_middleware_omits_not_set_correlation_on_denied_audit(
    monkeypatch,
):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/integration",
        "headers": [(b"content-length", b"0")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    token = correlation_id_var.set("<not-set>")
    try:
        from unittest.mock import patch

        with patch(
            "src.services.query_control_plane_service.app.enterprise_readiness.emit_audit_event"
        ) as audit:
            response = await middleware(request, _call_next)
    finally:
        correlation_id_var.reset(token)

    assert response.status_code == 403
    assert audit.call_args.kwargs["correlation_id"] is None


@pytest.mark.asyncio
async def test_control_plane_enterprise_middleware_omits_not_set_correlation_on_write_audit(
    monkeypatch,
):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/integration",
        "headers": [(b"content-length", b"0")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    token = correlation_id_var.set("<not-set>")
    try:
        from unittest.mock import patch

        with patch(
            "src.services.query_control_plane_service.app.enterprise_readiness.emit_audit_event"
        ) as audit:
            response = await middleware(request, _call_next)
    finally:
        correlation_id_var.reset(token)

    assert response.status_code == 200
    assert audit.call_args.kwargs["correlation_id"] is None


def test_control_plane_emit_audit_event_preserves_none_correlation():
    from unittest.mock import patch

    with patch(
        "src.services.query_control_plane_service.app.enterprise_readiness.logger.info"
    ) as logger_info:
        emit_audit_event(
            action="WRITE /api/v1/integration",
            actor_id="actor-1",
            tenant_id="tenant-1",
            role="ops",
            correlation_id=None,
            metadata={"status_code": 202},
        )

    audit_payload = logger_info.call_args.kwargs["extra"]["audit"]
    assert audit_payload["correlation_id"] is None
