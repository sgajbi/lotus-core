"""Verify corporate-action manifest route scope and command delegation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.logging_utils import correlation_id_var, request_id_var, trace_id_var
from starlette.requests import Request

from src.services.ingestion_service.app.DTOs.corporate_action_manifest_dto import (
    CorporateActionManifestIngestionRequest,
)
from src.services.ingestion_service.app.routers.corporate_action_manifests import (
    ingest_corporate_action_manifests,
)


def _request() -> CorporateActionManifestIngestionRequest:
    return CorporateActionManifestIngestionRequest.model_validate(
        {
            "manifests": [
                {
                    "corporate_action_event_id": "EVENT_001",
                    "tenant_id": "TENANT_SG",
                    "legal_book_id": "BOOK_SG_PB",
                    "portfolio_id": "PORTFOLIO_001",
                    "linked_transaction_group_id": "GROUP_001",
                    "parent_event_reference": "PARENT_001",
                    "corporate_action_type": "SPIN_OFF",
                    "version": 1,
                    "completion_declared": False,
                    "expected_children": [],
                    "source": {
                        "source_system": "corporate-actions-master",
                        "source_record_id": "EVENT_001",
                        "source_revision": "revision-1",
                        "source_content_hash": "a" * 64,
                        "observed_at": "2026-08-11T02:15:00Z",
                    },
                }
            ]
        }
    )


def _http_request(tenant_id: str) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/corporate-action-manifests",
            "headers": [
                (b"x-idempotency-key", b"manifest-001"),
                (b"x-tenant-id", tenant_id.encode()),
            ],
            "query_string": b"",
            "server": ("test", 80),
            "scheme": "http",
        }
    )
    request.state.tenant_context = TenantContext(tenant_id=TenantId(tenant_id))
    return request


@pytest.mark.asyncio
async def test_route_delegates_typed_scoped_manifest_batch() -> None:
    handler = AsyncMock()
    handler.ingest_corporate_action_manifests.return_value = SimpleNamespace(
        message="Accepted.",
        entity_type="corporate_action_manifest",
        job_id="job-manifest-001",
        accepted_count=1,
    )

    tokens = (
        correlation_id_var.set("corr-manifest-001"),
        request_id_var.set("request-manifest-001"),
        trace_id_var.set("trace-manifest-001"),
    )
    try:
        response = await ingest_corporate_action_manifests(
            _request(),
            _http_request("TENANT_SG"),
            handler,
        )
    finally:
        trace_id_var.reset(tokens[2])
        request_id_var.reset(tokens[1])
        correlation_id_var.reset(tokens[0])

    command = handler.ingest_corporate_action_manifests.await_args.args[0]
    assert command.endpoint == "/ingest/corporate-action-manifests"
    assert command.idempotency_key == "manifest-001"
    assert command.entity_type == "corporate_action_manifest"
    assert command.tenant_context.tenant_id_text == "TENANT_SG"
    assert tuple(command.records) == tuple(_request().manifests)
    assert response.job_id == "job-manifest-001"


@pytest.mark.asyncio
async def test_route_rejects_cross_tenant_manifest_before_command() -> None:
    handler = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await ingest_corporate_action_manifests(
            _request(),
            _http_request("TENANT_OTHER"),
            handler,
        )

    assert exc_info.value.status_code == 403
    handler.ingest_corporate_action_manifests.assert_not_awaited()
