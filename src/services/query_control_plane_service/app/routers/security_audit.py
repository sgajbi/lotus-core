"""Protected Query Control Plane security-audit support endpoint."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status
from portfolio_common.domain.security_audit import (
    SecurityAuditComponent,
    SecurityAuditDecision,
)
from portfolio_common.infrastructure_errors import DatabaseUnavailable

from ..application.security_audit_query import SecurityAuditQueryService
from ..contracts.security_audit import (
    SecurityAuditEventResponse,
    SecurityAuditPageResponse,
)
from ..dependencies import get_security_audit_query_service
from .response_helpers import (
    LEGACY_DETAIL_RESPONSE_SCHEMA,
    problem_example,
    problem_or_validation_response,
    problem_with_alternate_json_response,
    raise_problem,
)

router = APIRouter(tags=["Security Audit Support"])

VERIFIED_TENANT_REQUIRED = problem_example(
    status_code=status.HTTP_403_FORBIDDEN,
    title="Verified tenant context required",
    detail="The request does not carry verified tenant authority.",
    error_code="QCP_SECURITY_AUDIT_TENANT_CONTEXT_REQUIRED",
    instance="/support/security-audit/events",
)
INVALID_QUERY = problem_example(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    title="Security-audit query invalid",
    detail="The requested evidence window or cursor is outside governed bounds.",
    error_code="QCP_SECURITY_AUDIT_QUERY_INVALID",
    instance="/support/security-audit/events",
)
QUERY_UNAVAILABLE = problem_example(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    title="Security-audit evidence unavailable",
    detail="Durable security-audit evidence is temporarily unavailable.",
    error_code="QCP_SECURITY_AUDIT_QUERY_UNAVAILABLE",
    instance="/support/security-audit/events",
)
AUTHORIZATION_DENIED_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["detail", "reason"],
}


@router.get(
    "/support/security-audit/events",
    response_model=SecurityAuditPageResponse,
    responses={
        status.HTTP_403_FORBIDDEN: problem_with_alternate_json_response(
            "Verified tenant authority is missing.",
            VERIFIED_TENANT_REQUIRED,
            json_schema=AUTHORIZATION_DENIED_SCHEMA,
            json_example={
                "detail": "authorization_policy_denied",
                "reason": "missing_headers:x-tenant-id",
            },
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: problem_or_validation_response(
            "Evidence query bounds or cursor are invalid.", INVALID_QUERY
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: problem_with_alternate_json_response(
            "Durable evidence cannot currently be queried.",
            QUERY_UNAVAILABLE,
            json_schema=LEGACY_DETAIL_RESPONSE_SCHEMA,
            json_example={"detail": "security_audit_unavailable"},
        ),
    },
    summary="List tenant-bound durable access-decision evidence",
    description=(
        "Returns typed, append-only access-decision evidence for the verified request tenant. "
        "The query is limited to 31 days and descending keyset pagination. Request bodies, "
        "headers, concrete URLs, secrets, and raw exceptions are never returned."
    ),
)
async def list_security_audit_events(
    request: Request,
    occurred_from: datetime = Query(description="Inclusive UTC lower time boundary."),
    occurred_to: datetime = Query(description="Inclusive UTC upper time boundary."),
    page_size: int = Query(
        default=100,
        ge=1,
        le=200,
        description="Maximum evidence records returned in this page.",
    ),
    cursor_occurred_at: datetime | None = Query(
        default=None,
        description="Prior page's UTC time cursor; requires cursor_event_id.",
    ),
    cursor_event_id: str | None = Query(
        default=None,
        description="Prior page's UUID tie-break cursor; requires cursor_occurred_at.",
    ),
    component: SecurityAuditComponent | None = Query(
        default=None,
        description="Optional governed Core component filter.",
    ),
    decision: SecurityAuditDecision | None = Query(
        default=None,
        description="Optional ALLOW or DENY decision filter.",
    ),
    service: SecurityAuditQueryService = Depends(get_security_audit_query_service),
) -> SecurityAuditPageResponse:
    tenant_id = getattr(request.state, "enterprise_verified_tenant_id", None)
    if not isinstance(tenant_id, str) or not tenant_id:
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Verified tenant context required",
            detail="The request does not carry verified tenant authority.",
            error_code="QCP_SECURITY_AUDIT_TENANT_CONTEXT_REQUIRED",
        )
    try:
        page = await service.list_events(
            tenant_id=tenant_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            page_size=page_size,
            cursor_occurred_at=cursor_occurred_at,
            cursor_event_id=cursor_event_id,
            component=component,
            decision=decision,
        )
    except ValueError:
        raise_problem(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Security-audit query invalid",
            detail="The requested evidence window or cursor is outside governed bounds.",
            error_code="QCP_SECURITY_AUDIT_QUERY_INVALID",
        )
    except DatabaseUnavailable:
        raise_problem(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            title="Security-audit evidence unavailable",
            detail="Durable security-audit evidence is temporarily unavailable.",
            error_code="QCP_SECURITY_AUDIT_QUERY_UNAVAILABLE",
        )
    return SecurityAuditPageResponse(
        events=[SecurityAuditEventResponse.model_validate(event) for event in page.events],
        next_cursor_occurred_at=page.next_cursor_occurred_at,
        next_cursor_event_id=page.next_cursor_event_id,
    )
