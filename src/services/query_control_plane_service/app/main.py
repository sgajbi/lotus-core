import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from portfolio_common.health import create_health_router
from portfolio_common.http_app_bootstrap import configure_standard_http_app, include_routers
from portfolio_common.logging_utils import (
    correlation_id_var,
    generate_correlation_id,
    setup_logging,
)

from .contracts import (
    ADVISORY_SIMULATION_CONTRACT_VERSION,
    ADVISORY_SIMULATION_CONTRACT_VERSION_HEADER,
    ADVISORY_SIMULATION_EXECUTION_PATH,
    PROBLEM_TYPE_PREFIX,
    CanonicalSimulationContractError,
    CanonicalSimulationErrorCode,
)
from .enterprise_readiness import (
    build_enterprise_audit_middleware,
    validate_enterprise_runtime_config,
)
from .routers import (
    advisory_simulation,
    analytics_inputs,
    capabilities,
    integration,
    operations,
    simulation,
)

SERVICE_PREFIX = "QCP"
SERVICE_NAME = "query_control_plane_service"
setup_logging()
logger = logging.getLogger(__name__)
validate_enterprise_runtime_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Query Control Plane Service starting up...")
    yield
    logger.info(
        "Query Control Plane Service shutting down. Waiting for in-flight requests to complete..."
    )
    logger.info("Query Control Plane Service has shut down gracefully.")


app = FastAPI(
    title="Lotus Core Query Control Plane API",
    description=(
        "Lotus Core control-plane APIs for integration contracts, operational support, "
        "and simulation workflows. Core read-plane endpoints remain in query_service."
    ),
    version="0.2.0",
    contact={"name": "Lotus Platform Engineering"},
    lifespan=lifespan,
)
app.middleware("http")(build_enterprise_audit_middleware())
configure_standard_http_app(
    app,
    service_name=SERVICE_NAME,
    service_prefix=SERVICE_PREFIX,
    logger=logger,
    id_generator=lambda prefix: generate_correlation_id(prefix),
)

health_router = create_health_router("db")
include_routers(
    app,
    health_router,
    operations.router,
    integration.router,
    advisory_simulation.router,
    analytics_inputs.router,
    capabilities.router,
    simulation.router,
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


@app.exception_handler(CanonicalSimulationContractError)
async def canonical_simulation_contract_error_handler(
    request,
    exc: CanonicalSimulationContractError,
):
    return _canonical_simulation_problem(
        status_code=exc.status_code,
        title="Canonical Simulation Contract Error",
        detail=exc.detail,
        instance=str(request.url.path),
        error_code=exc.error_code,
    )


@app.exception_handler(RequestValidationError)
async def canonical_simulation_validation_error_handler(request, exc: RequestValidationError):
    if request.url.path != ADVISORY_SIMULATION_EXECUTION_PATH:
        return await request_validation_exception_handler(request, exc)
    return _canonical_simulation_problem(
        status_code=422,
        title="Canonical Simulation Request Validation Failed",
        detail="Request payload does not satisfy the canonical simulation contract.",
        instance=str(request.url.path),
        error_code=CanonicalSimulationErrorCode.REQUEST_VALIDATION_FAILED,
    )


@app.exception_handler(Exception)
async def canonical_simulation_unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    if request.url.path == ADVISORY_SIMULATION_EXECUTION_PATH:
        logger.exception("Canonical simulation execution failed", exc_info=exc)
        return _canonical_simulation_problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Canonical Simulation Execution Failed",
            detail="Canonical simulation execution failed inside lotus-core.",
            instance=str(request.url.path),
            error_code=CanonicalSimulationErrorCode.EXECUTION_FAILED,
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
