"""Verify the fixed-income authority route delegates governed lifecycle work."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.logging_utils import correlation_id_var, request_id_var, trace_id_var
from starlette.requests import Request

from src.services.ingestion_service.app.DTOs.fixed_income_book_cost_authority_dto import (
    FixedIncomeBookCostAuthorityIngestionRequest,
)
from src.services.ingestion_service.app.routers.fixed_income_book_cost import (
    ingest_fixed_income_book_cost_authorities,
)


def _authority_request() -> FixedIncomeBookCostAuthorityIngestionRequest:
    return FixedIncomeBookCostAuthorityIngestionRequest.model_validate(
        {
            "authorities": [
                {
                    "authority_type": "POLICY_ASSIGNMENT",
                    "header": {
                        "scope": {
                            "tenant_id": "TENANT_SG",
                            "legal_book_id": "BOOK_SG_PB",
                            "portfolio_id": "PORTFOLIO_001",
                            "security_id": "BOND_001",
                            "lot_id": "LOT_001",
                        },
                        "source": {
                            "source_system": "accounting-policy-master",
                            "source_record_id": "assignment-001",
                            "source_revision": "revision-1",
                            "source_version": 1,
                            "observed_at": "2026-08-03T09:00:00+08:00",
                        },
                        "status": "ACTIVE",
                        "valid_from": "2026-08-01",
                    },
                    "policy_id": "IFRS9_EIR_LOCAL",
                    "policy_version": 1,
                    "assignment_reason": "Approved accounting treatment",
                }
            ]
        }
    )


@pytest.mark.asyncio
async def test_route_passes_typed_authority_and_idempotency_to_command_handler() -> None:
    command_handler = AsyncMock()
    command_handler.ingest_fixed_income_book_cost_authorities.return_value = SimpleNamespace(
        message="Accepted.",
        entity_type="fixed_income_book_cost_authority",
        job_id="job-book-cost-001",
        accepted_count=1,
    )
    http_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/fixed-income-book-cost-authorities",
            "headers": [
                (b"x-idempotency-key", b"book-cost-001"),
                (b"x-tenant-id", b"TENANT_SG"),
            ],
            "query_string": b"",
            "server": ("test", 80),
            "scheme": "http",
        }
    )
    http_request.state.tenant_context = TenantContext(tenant_id=TenantId("TENANT_SG"))
    tokens = (
        correlation_id_var.set("corr-book-cost-001"),
        request_id_var.set("request-book-cost-001"),
        trace_id_var.set("trace-book-cost-001"),
    )
    try:
        response = await ingest_fixed_income_book_cost_authorities(
            _authority_request(),
            http_request,
            command_handler,
        )
    finally:
        trace_id_var.reset(tokens[2])
        request_id_var.reset(tokens[1])
        correlation_id_var.reset(tokens[0])

    command = command_handler.ingest_fixed_income_book_cost_authorities.await_args.args[0]
    assert command.endpoint == "/ingest/fixed-income-book-cost-authorities"
    assert command.idempotency_key == "book-cost-001"
    assert command.entity_type == "fixed_income_book_cost_authority"
    assert command.tenant_context.tenant_id_text == "TENANT_SG"
    assert tuple(command.records) == tuple(_authority_request().authorities)
    assert response.job_id == "job-book-cost-001"
    assert response.idempotency_key == "book-cost-001"


@pytest.mark.asyncio
async def test_route_rejects_authority_for_another_authenticated_tenant() -> None:
    command_handler = AsyncMock()
    http_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/fixed-income-book-cost-authorities",
            "headers": [(b"x-tenant-id", b"TENANT_OTHER")],
            "query_string": b"",
            "server": ("test", 80),
            "scheme": "http",
        }
    )
    http_request.state.tenant_context = TenantContext(tenant_id=TenantId("TENANT_OTHER"))

    with pytest.raises(HTTPException) as exc_info:
        await ingest_fixed_income_book_cost_authorities(
            _authority_request(),
            http_request,
            command_handler,
        )

    assert exc_info.value.status_code == 403
    command_handler.ingest_fixed_income_book_cost_authorities.assert_not_awaited()
