"""Bounded operations-support route for corporate-action event execution."""

from fastapi import APIRouter, Depends, Header, Path, Query, status

from ..application.corporate_action_support import MAX_SUPPORT_SKIP, CorporateActionSupportService
from ..contracts.corporate_action_support import CorporateActionEventSupportListResponse
from ..dependencies import get_corporate_action_support_service
from .response_helpers import problem_example, problem_response, raise_problem

router = APIRouter(prefix="/support/portfolios", tags=["Operations Support"])

NOT_FOUND = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Corporate-action support scope not found",
    detail="Requested corporate-action support scope was not found.",
    error_code="QCP_CORPORATE_ACTION_SUPPORT_NOT_FOUND",
    instance="/support/portfolios/PORT-001/corporate-action-events",
)
FORBIDDEN = problem_example(
    status_code=status.HTTP_403_FORBIDDEN,
    title="Corporate-action support scope forbidden",
    detail="Requested tenant does not match authenticated tenant scope.",
    error_code="QCP_CORPORATE_ACTION_SUPPORT_FORBIDDEN",
    instance="/support/portfolios/PORT-001/corporate-action-events",
)
INVALID = problem_example(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    title="Corporate-action support request invalid",
    detail="Requested corporate-action support filters or paging are invalid.",
    error_code="QCP_CORPORATE_ACTION_SUPPORT_INVALID",
    instance="/support/portfolios/PORT-001/corporate-action-events",
)


@router.get(
    "/{portfolio_id}/corporate-action-events",
    response_model=CorporateActionEventSupportListResponse,
    responses={
        status.HTTP_403_FORBIDDEN: problem_response("Tenant scope mismatch.", FORBIDDEN),
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio or corporate-action event not found.", NOT_FOUND
        ),
        status.HTTP_422_UNPROCESSABLE_CONTENT: problem_response(
            "Filters or paging are outside governed bounds.", INVALID
        ),
    },
    summary="List current corporate-action event execution posture",
    description=(
        "What: Returns a bounded, book-scoped operations projection of current corporate-action "
        "manifest authority, readiness, and fenced execution-release progress without lease "
        "secrets or member payloads. How: Query Control Plane reads the current persisted "
        "generation through exact tenant, legal-book, and portfolio predicates and derives lease "
        "state from the PostgreSQL clock. When: Use this route to triage incomplete, invalid, "
        "retrying, failed, superseded, or completed corporate-action cohorts; use governed replay "
        "or reprocessing controls for recovery rather than direct database mutation."
    ),
)
async def list_corporate_action_event_support(
    portfolio_id: str = Path(
        ...,
        min_length=1,
        examples=["PB_SG_GLOBAL_BAL_001"],
        description="Portfolio identifier within the governed tenant and legal-book scope.",
    ),
    tenant_id: str = Query(
        ...,
        min_length=1,
        examples=["TENANT-SG"],
        description="Tenant identifier; must equal the authenticated X-Tenant-Id header.",
    ),
    legal_book_id: str = Query(
        ...,
        min_length=1,
        examples=["PB-SG-01"],
        description="Legal-book identifier used to prevent cross-book evidence disclosure.",
    ),
    corporate_action_event_id: str | None = Query(
        None,
        min_length=1,
        description="Optional exact corporate-action event identifier filter.",
    ),
    readiness_status: str | None = Query(
        None,
        min_length=1,
        description="Optional readiness status filter; values are validated fail-closed.",
    ),
    execution_status: str | None = Query(
        None,
        min_length=1,
        description="Optional execution-release status filter; values are validated fail-closed.",
    ),
    skip: int = Query(
        0,
        ge=0,
        le=MAX_SUPPORT_SKIP,
        description="Zero-based offset within the deterministic current-event ordering.",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Maximum current-event records to return; capped at 100.",
    ),
    x_tenant_id: str = Header(
        ...,
        min_length=1,
        alias="X-Tenant-Id",
        description="Authenticated tenant scope enforced against the tenant_id query parameter.",
    ),
    service: CorporateActionSupportService = Depends(get_corporate_action_support_service),
) -> CorporateActionEventSupportListResponse:
    normalized_tenant_id = tenant_id.strip()
    if not normalized_tenant_id or normalized_tenant_id != x_tenant_id.strip():
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Corporate-action support scope forbidden",
            detail="Requested tenant does not match authenticated tenant scope.",
            error_code="QCP_CORPORATE_ACTION_SUPPORT_FORBIDDEN",
        )
    try:
        return await service.list_current(
            tenant_id=normalized_tenant_id,
            legal_book_id=legal_book_id,
            portfolio_id=portfolio_id,
            corporate_action_event_id=corporate_action_event_id,
            readiness_status=readiness_status,
            execution_status=execution_status,
            skip=skip,
            limit=limit,
        )
    except LookupError:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Corporate-action support scope not found",
            detail="Requested corporate-action support scope was not found.",
            error_code="QCP_CORPORATE_ACTION_SUPPORT_NOT_FOUND",
        )
    except ValueError:
        raise_problem(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Corporate-action support request invalid",
            detail="Requested corporate-action support filters or paging are invalid.",
            error_code="QCP_CORPORATE_ACTION_SUPPORT_INVALID",
        )
