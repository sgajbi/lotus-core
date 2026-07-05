from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Callable

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from portfolio_common.logging_utils import correlation_id_var

from .contracts import (
    ADVISORY_SIMULATION_CONTRACT_VERSION,
    ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER,
    PROBLEM_TYPE_PREFIX,
    CanonicalSimulationContractError,
    CanonicalSimulationErrorCode,
)
from .contracts.advisory_simulation import ADVISORY_SIMULATION_EXECUTION_PATH
from .routers.response_helpers import QueryControlPlaneProblem, build_problem_payload


@dataclass(frozen=True)
class EndpointExceptionMapper:
    path: str
    log_message: str
    validation_title: str
    validation_detail: str
    validation_error_code: CanonicalSimulationErrorCode
    execution_title: str
    execution_detail: str
    execution_error_code: CanonicalSimulationErrorCode

    def matches(self, request: Request) -> bool:
        return request.url.path == self.path


_ADVISORY_SIMULATION_EXCEPTION_MAPPER = EndpointExceptionMapper(
    path=ADVISORY_SIMULATION_EXECUTION_PATH,
    log_message="Canonical simulation execution failed",
    validation_title="Canonical Simulation Request Validation Failed",
    validation_detail="Request payload does not satisfy the canonical simulation contract.",
    validation_error_code=CanonicalSimulationErrorCode.REQUEST_VALIDATION_FAILED,
    execution_title="Canonical Simulation Execution Failed",
    execution_detail="Canonical simulation execution failed inside lotus-core.",
    execution_error_code=CanonicalSimulationErrorCode.EXECUTION_FAILED,
)
_ENDPOINT_EXCEPTION_MAPPERS = (_ADVISORY_SIMULATION_EXCEPTION_MAPPER,)


def register_query_control_plane_exception_handlers(
    app: FastAPI,
    *,
    logger: logging.Logger,
) -> None:
    app.add_exception_handler(QueryControlPlaneProblem, _query_control_plane_problem_handler)
    app.add_exception_handler(
        CanonicalSimulationContractError,
        _canonical_simulation_contract_error_handler,
    )
    app.add_exception_handler(
        RequestValidationError,
        _request_validation_error_handler,
    )
    app.add_exception_handler(
        Exception,
        _unhandled_exception_handler(logger),
    )


async def _query_control_plane_problem_handler(
    request: Request,
    exc: QueryControlPlaneProblem,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/problem+json",
        content=build_problem_payload(
            problem=exc,
            instance=str(request.url.path),
            correlation_id=correlation_id_var.get() or "",
        ),
    )


def _canonical_simulation_problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    instance: str,
    error_code: CanonicalSimulationErrorCode,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"{PROBLEM_TYPE_PREFIX}/{error_code.value.lower()}",
            "title": title,
            "status": status_code,
            "detail": detail,
            "instance": instance,
            "error_code": error_code.value,
            "contract_version": ADVISORY_SIMULATION_CONTRACT_VERSION,
            "correlation_id": correlation_id_var.get() or "",
        },
    )
    response.headers[ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER] = (
        ADVISORY_SIMULATION_CONTRACT_VERSION
    )
    return response


async def _canonical_simulation_contract_error_handler(
    request: Request,
    exc: CanonicalSimulationContractError,
) -> JSONResponse:
    return _canonical_simulation_problem(
        status_code=exc.status_code,
        title="Canonical Simulation Contract Error",
        detail=exc.detail,
        instance=str(request.url.path),
        error_code=exc.error_code,
    )


async def _request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
):
    mapper = _mapper_for(request)
    if mapper is None:
        return await request_validation_exception_handler(request, exc)
    return _canonical_simulation_problem(
        status_code=422,
        title=mapper.validation_title,
        detail=mapper.validation_detail,
        instance=str(request.url.path),
        error_code=mapper.validation_error_code,
    )


def _unhandled_exception_handler(
    logger: logging.Logger,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        mapper = _mapper_for(request)
        if mapper is not None:
            logger.exception(mapper.log_message, exc_info=exc)
            return _canonical_simulation_problem(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                title=mapper.execution_title,
                detail=mapper.execution_detail,
                instance=str(request.url.path),
                error_code=mapper.execution_error_code,
            )
        logger.critical(
            "Unhandled exception for request %s %s",
            request.method,
            request.url,
            exc_info=exc,
            extra={"correlation_id": correlation_id_var.get() or ""},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred. Please contact support.",
                "correlation_id": correlation_id_var.get() or "",
            },
        )

    return handler


def _mapper_for(request: Request) -> EndpointExceptionMapper | None:
    return next(
        (mapper for mapper in _ENDPOINT_EXCEPTION_MAPPERS if mapper.matches(request)),
        None,
    )
