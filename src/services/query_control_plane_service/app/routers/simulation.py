# src/services/query_control_plane_service/app/routers/simulation.py
from fastapi import APIRouter, Depends, HTTPException, Path, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.simulation_dto import (
    ProjectedPositionsResponse,
    ProjectedSummaryResponse,
    SimulationChangesResponse,
    SimulationChangeUpsertRequest,
    SimulationSessionCreateRequest,
    SimulationSessionResponse,
)
from src.services.query_service.app.services.simulation_service import SimulationService

router = APIRouter(prefix="/simulation-sessions", tags=["Simulation"])

SIMULATION_SESSION_NOT_FOUND_EXAMPLE = {"detail": "Simulation session SIM-20260310-0001 not found"}
SIMULATION_SESSION_INVALID_STATE_EXAMPLE = {
    "detail": "Simulation session SIM-20260310-0001 is not active"
}
SIMULATION_CHANGE_NOT_FOUND_EXAMPLE = {"detail": "Simulation change SIM-CHG-0001 not found"}
SIMULATION_PORTFOLIO_NOT_FOUND_EXAMPLE = {"detail": "Portfolio with id PORT-404 not found"}
SIMULATION_INTERNAL_ERROR_EXAMPLE = {"detail": "Failed to create simulation session."}


def _raise_simulation_mutation_error(exc: ValueError) -> None:
    detail = str(exc)
    if "not found" in detail.lower():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def get_simulation_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> SimulationService:
    return SimulationService(db)


@router.post(
    "",
    response_model=SimulationSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": SIMULATION_PORTFOLIO_NOT_FOUND_EXAMPLE}},
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected simulation session creation failure.",
            "content": {"application/json": {"example": SIMULATION_INTERNAL_ERROR_EXAMPLE}},
        },
    },
    description=(
        "Create a what-if simulation session for a booked portfolio. Use this endpoint for "
        "deterministic projected-state workflows such as gateway or manage sandbox edits. "
        "Do not use it as an analytics-input route or for advisory recommendation logic. "
        "The session provides an isolated control-plane sandbox for proposed changes and "
        "downstream projection endpoints."
    ),
)
async def create_simulation_session(
    request: SimulationSessionCreateRequest,
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.create_session(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SIMULATION_INTERNAL_ERROR_EXAMPLE["detail"],
        ) from exc


@router.get(
    "/{session_id}",
    response_model=SimulationSessionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Simulation session not found.",
            "content": {"application/json": {"example": SIMULATION_SESSION_NOT_FOUND_EXAMPLE}},
        },
    },
    description="Get simulation session metadata by session identifier.",
)
async def get_simulation_session(
    session_id: str = Path(
        ...,
        description="Simulation session identifier.",
        examples=["SIM-20260310-0001"],
    ),
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete(
    "/{session_id}",
    response_model=SimulationSessionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Simulation session not found.",
            "content": {"application/json": {"example": SIMULATION_SESSION_NOT_FOUND_EXAMPLE}},
        },
    },
    description=(
        "Close an active simulation session. Closed sessions remain queryable but reject "
        "further change mutations."
    ),
)
async def close_simulation_session(
    session_id: str = Path(
        ...,
        description="Simulation session identifier.",
        examples=["SIM-20260310-0001"],
    ),
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.close_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{session_id}/changes",
    response_model=SimulationChangesResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Simulation session not found.",
            "content": {"application/json": {"example": SIMULATION_SESSION_NOT_FOUND_EXAMPLE}},
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Simulation session is inactive or change request is invalid.",
            "content": {"application/json": {"example": SIMULATION_SESSION_INVALID_STATE_EXAMPLE}},
        },
    },
    description=(
        "Add or update simulation changes for a session. The returned payload reflects the "
        "current persisted change set after the mutation."
    ),
)
async def add_simulation_changes(
    request: SimulationChangeUpsertRequest,
    session_id: str = Path(
        ...,
        description="Simulation session identifier.",
        examples=["SIM-20260310-0001"],
    ),
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        payload = [item.model_dump() for item in request.changes]
        return await service.add_changes(session_id, payload)
    except ValueError as exc:
        _raise_simulation_mutation_error(exc)


@router.delete(
    "/{session_id}/changes/{change_id}",
    response_model=SimulationChangesResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Simulation session or change not found.",
            "content": {"application/json": {"example": SIMULATION_CHANGE_NOT_FOUND_EXAMPLE}},
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Simulation session is inactive or change request is invalid.",
            "content": {"application/json": {"example": SIMULATION_CHANGE_NOT_FOUND_EXAMPLE}},
        },
    },
    description="Delete a simulation change from a session.",
)
async def delete_simulation_change(
    session_id: str = Path(
        ...,
        description="Simulation session identifier.",
        examples=["SIM-20260310-0001"],
    ),
    change_id: str = Path(
        ...,
        description="Simulation change identifier.",
        examples=["SIM-CHG-0001"],
    ),
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.delete_change(session_id, change_id)
    except ValueError as exc:
        _raise_simulation_mutation_error(exc)


@router.get(
    "/{session_id}/projected-positions",
    response_model=ProjectedPositionsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Simulation session not found.",
            "content": {"application/json": {"example": SIMULATION_SESSION_NOT_FOUND_EXAMPLE}},
        },
    },
    description=(
        "Return deterministic projected holdings after applying the current simulation change "
        "set to the latest booked baseline positions. Use this for what-if state inspection, "
        "not for performance analytics, risk analytics, or advisory recommendation output."
    ),
)
async def get_projected_positions(
    session_id: str = Path(
        ...,
        description="Simulation session identifier.",
        examples=["SIM-20260310-0001"],
    ),
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.get_projected_positions(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{session_id}/projected-summary",
    response_model=ProjectedSummaryResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Simulation session not found.",
            "content": {"application/json": {"example": SIMULATION_SESSION_NOT_FOUND_EXAMPLE}},
        },
    },
    description=(
        "Return deterministic projected state summary metrics for a simulation session after "
        "applying the current change set. This is a portfolio-state sandbox summary, not a "
        "recommendation, suitability, or downstream analytics result."
    ),
)
async def get_projected_summary(
    session_id: str = Path(
        ...,
        description="Simulation session identifier.",
        examples=["SIM-20260310-0001"],
    ),
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.get_projected_summary(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
