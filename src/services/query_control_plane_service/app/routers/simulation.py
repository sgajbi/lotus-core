# src/services/query_service/app/routers/simulation.py
from fastapi import APIRouter, Depends, HTTPException, status
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


def get_simulation_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> SimulationService:
    return SimulationService(db)


@router.post(
    "",
    response_model=SimulationSessionResponse,
    status_code=status.HTTP_201_CREATED,
    description="Create a simulation session for a portfolio.",
)
async def create_simulation_session(
    request: SimulationSessionCreateRequest,
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.create_session(request)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "/{session_id}",
    response_model=SimulationSessionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Simulation session not found."},
    },
    description="Get simulation session metadata by session identifier.",
)
async def get_simulation_session(
    session_id: str,
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
        status.HTTP_404_NOT_FOUND: {"description": "Simulation session not found."},
    },
    description="Close an active simulation session.",
)
async def close_simulation_session(
    session_id: str,
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
        status.HTTP_400_BAD_REQUEST: {
            "description": "Simulation session is inactive or change request is invalid."
        },
    },
    description="Add or update simulation changes for a session.",
)
async def add_simulation_changes(
    session_id: str,
    request: SimulationChangeUpsertRequest,
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        payload = [item.model_dump() for item in request.changes]
        return await service.add_changes(session_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete(
    "/{session_id}/changes/{change_id}",
    response_model=SimulationChangesResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Simulation session is inactive or change request is invalid."
        },
    },
    description="Delete a simulation change from a session.",
)
async def delete_simulation_change(
    session_id: str,
    change_id: str,
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.delete_change(session_id, change_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/{session_id}/projected-positions",
    response_model=ProjectedPositionsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Simulation session not found."},
    },
    description="Return projected positions after applying session changes.",
)
async def get_projected_positions(
    session_id: str,
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
        status.HTTP_404_NOT_FOUND: {"description": "Simulation session not found."},
    },
    description="Return projected summary metrics for a simulation session.",
)
async def get_projected_summary(
    session_id: str,
    service: SimulationService = Depends(get_simulation_service),
):
    try:
        return await service.get_projected_summary(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
