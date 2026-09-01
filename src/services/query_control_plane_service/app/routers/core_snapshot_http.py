"""HTTP error mapping for the governed Core snapshot route family."""

from typing import cast

from fastapi import status

from ..application.core_snapshot.governance import SnapshotGovernanceContext
from ..application.core_snapshot.service import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
    CoreSnapshotService,
    CoreSnapshotUnavailableSectionError,
)
from ..contracts.core_snapshot import CoreSnapshotRequest, CoreSnapshotResponse
from .response_helpers import raise_problem

HTTP_422_UNPROCESSABLE_CONTENT = 422


async def core_snapshot_response_or_http_error(
    *,
    service: CoreSnapshotService,
    portfolio_id: str,
    request: CoreSnapshotRequest,
    governance: SnapshotGovernanceContext,
) -> CoreSnapshotResponse:
    """Execute a governed snapshot and expose only bounded HTTP problem details."""

    try:
        response = await service.get_core_snapshot(
            portfolio_id=portfolio_id,
            request=request,
            governance=governance,
        )
        return cast(CoreSnapshotResponse, response)
    except CoreSnapshotBadRequestError as exc:
        raise_problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Core snapshot request is invalid",
            detail="Core snapshot request is invalid.",
            error_code="QCP_CORE_SNAPSHOT_INVALID_REQUEST",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotNotFoundError as exc:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Core snapshot not found",
            detail="Portfolio or simulation session was not found.",
            error_code="QCP_CORE_SNAPSHOT_NOT_FOUND",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotConflictError as exc:
        raise_problem(
            status_code=status.HTTP_409_CONFLICT,
            title="Core snapshot conflict",
            detail=(
                "Core snapshot request conflicts with the current portfolio or simulation state."
            ),
            error_code="QCP_CORE_SNAPSHOT_CONFLICT",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotUnavailableSectionError as exc:
        raise_problem(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            title="Core snapshot section unavailable",
            detail=(
                "Requested core snapshot section cannot be fulfilled from available source data."
            ),
            error_code="QCP_CORE_SNAPSHOT_UNAVAILABLE_SECTION",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    raise AssertionError("problem response helper returned unexpectedly")
