# src/services/query_control_plane_service/app/routers/simulation.py
from fastapi import APIRouter, Depends, Path, status

from src.services.query_service.app.dtos.simulation_dto import (
    ProjectedPositionsResponse,
    ProjectedSummaryResponse,
    SimulationChangesResponse,
    SimulationChangeUpsertRequest,
    SimulationSessionCreateRequest,
    SimulationSessionResponse,
)
from src.services.query_service.app.services.simulation_service import (
    SimulationChangeNotFoundError,
    SimulationMutationInvalidError,
    SimulationPortfolioNotFoundError,
    SimulationService,
    SimulationSessionNotFoundError,
)

from ..dependencies import get_simulation_service
from .response_helpers import problem_example, problem_response, raise_problem

router = APIRouter(prefix="/simulation-sessions", tags=["Simulation"])

SIMULATION_SESSION_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Simulation session not found",
    detail="Simulation session was not found.",
    error_code="QCP_SIMULATION_SESSION_NOT_FOUND",
    instance="/simulation-sessions/SIM-20260310-0001",
    metadata={"source_product": "SimulationSession"},
)
SIMULATION_SESSION_INVALID_STATE_EXAMPLE = {
    **problem_example(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Simulation mutation is invalid",
        detail="Simulation mutation request is invalid for the current session state.",
        error_code="QCP_SIMULATION_MUTATION_INVALID",
        instance="/simulation-sessions/SIM-20260310-0001/changes",
        metadata={"source_product": "SimulationSession"},
    )
}
SIMULATION_CHANGE_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Simulation change not found",
    detail="Simulation change was not found.",
    error_code="QCP_SIMULATION_CHANGE_NOT_FOUND",
    instance="/simulation-sessions/SIM-20260310-0001/changes/SIM-CHG-0001",
    metadata={"source_product": "SimulationSession"},
)
SIMULATION_PORTFOLIO_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Simulation portfolio not found",
    detail="Portfolio for simulation session creation was not found.",
    error_code="QCP_SIMULATION_PORTFOLIO_NOT_FOUND",
    instance="/simulation-sessions",
    metadata={"source_product": "SimulationSession"},
)
SIMULATION_INTERNAL_ERROR_EXAMPLE = problem_example(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    title="Simulation session creation failed",
    detail="Failed to create simulation session.",
    error_code="QCP_SIMULATION_CREATE_FAILED",
    instance="/simulation-sessions",
    metadata={"source_product": "SimulationSession"},
)


def _raise_simulation_resource_not_found(exc: Exception) -> None:
    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Simulation resource not found",
        detail="Simulation resource was not found.",
        error_code="QCP_SIMULATION_RESOURCE_NOT_FOUND",
        metadata={"source_product": "SimulationSession", "reason": exc.__class__.__name__},
    )


def _raise_simulation_mutation_invalid(exc: Exception) -> None:
    raise_problem(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Simulation mutation is invalid",
        detail="Simulation mutation request is invalid for the current session state.",
        error_code="QCP_SIMULATION_MUTATION_INVALID",
        metadata={"source_product": "SimulationSession", "reason": exc.__class__.__name__},
    )


def _raise_simulation_not_found(exc: ValueError) -> None:
    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Simulation session not found",
        detail="Simulation session was not found.",
        error_code="QCP_SIMULATION_SESSION_NOT_FOUND",
        metadata={"source_product": "SimulationSession", "reason": exc.__class__.__name__},
    )


@router.post(
    "",
    response_model=SimulationSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio not found.",
            SIMULATION_PORTFOLIO_NOT_FOUND_EXAMPLE,
        ),
        status.HTTP_500_INTERNAL_SERVER_ERROR: problem_response(
            "Unexpected simulation session creation failure.",
            SIMULATION_INTERNAL_ERROR_EXAMPLE,
        ),
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
    except SimulationPortfolioNotFoundError as exc:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Simulation portfolio not found",
            detail="Portfolio for simulation session creation was not found.",
            error_code="QCP_SIMULATION_PORTFOLIO_NOT_FOUND",
            metadata={"source_product": "SimulationSession", "reason": exc.__class__.__name__},
        )
    except Exception as exc:
        raise_problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Simulation session creation failed",
            detail="Failed to create simulation session.",
            error_code="QCP_SIMULATION_CREATE_FAILED",
            metadata={"source_product": "SimulationSession", "reason": exc.__class__.__name__},
        )


@router.get(
    "/{session_id}",
    response_model=SimulationSessionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Simulation session not found.",
            SIMULATION_SESSION_NOT_FOUND_EXAMPLE,
        ),
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
    except SimulationSessionNotFoundError as exc:
        _raise_simulation_not_found(exc)


@router.delete(
    "/{session_id}",
    response_model=SimulationSessionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Simulation session not found.",
            SIMULATION_SESSION_NOT_FOUND_EXAMPLE,
        ),
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
    except SimulationSessionNotFoundError as exc:
        _raise_simulation_not_found(exc)


@router.post(
    "/{session_id}/changes",
    response_model=SimulationChangesResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Simulation session not found.",
            SIMULATION_SESSION_NOT_FOUND_EXAMPLE,
        ),
        status.HTTP_400_BAD_REQUEST: problem_response(
            "Simulation session is inactive or change request is invalid.",
            SIMULATION_SESSION_INVALID_STATE_EXAMPLE,
        ),
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
    except SimulationSessionNotFoundError as exc:
        _raise_simulation_resource_not_found(exc)
    except SimulationMutationInvalidError as exc:
        _raise_simulation_mutation_invalid(exc)


@router.delete(
    "/{session_id}/changes/{change_id}",
    response_model=SimulationChangesResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Simulation session or change not found.",
            SIMULATION_CHANGE_NOT_FOUND_EXAMPLE,
        ),
        status.HTTP_400_BAD_REQUEST: problem_response(
            "Simulation session is inactive or change request is invalid.",
            SIMULATION_SESSION_INVALID_STATE_EXAMPLE,
        ),
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
    except (SimulationSessionNotFoundError, SimulationChangeNotFoundError) as exc:
        _raise_simulation_resource_not_found(exc)
    except SimulationMutationInvalidError as exc:
        _raise_simulation_mutation_invalid(exc)


@router.get(
    "/{session_id}/projected-positions",
    response_model=ProjectedPositionsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Simulation session not found.",
            SIMULATION_SESSION_NOT_FOUND_EXAMPLE,
        ),
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
    except SimulationSessionNotFoundError as exc:
        _raise_simulation_not_found(exc)


@router.get(
    "/{session_id}/projected-summary",
    response_model=ProjectedSummaryResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Simulation session not found.",
            SIMULATION_SESSION_NOT_FOUND_EXAMPLE,
        ),
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
    except SimulationSessionNotFoundError as exc:
        _raise_simulation_not_found(exc)
