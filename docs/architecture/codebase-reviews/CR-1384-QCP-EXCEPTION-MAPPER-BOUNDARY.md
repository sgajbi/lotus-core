# CR-1384 QCP Exception Mapper Boundary

- Date: 2026-07-06
- Status: Hardened locally
- GitHub issue: #536
- Control taxonomy: architecture, API contract quality, runtime composition, testability

## Objective

Keep query-control-plane app bootstrap free of endpoint-specific business-contract behavior while
preserving canonical advisory simulation problem responses.

## Finding

`query_control_plane_service/app/main.py` imported the advisory simulation execution path and
canonical simulation error vocabulary, then branched inside global request-validation and unhandled
exception handlers based on that path. That made app bootstrap own endpoint-specific API contract
mapping.

## Change

Added `query_control_plane_service.app.exception_mappers` with a typed endpoint exception mapper
registry. `main.py` now calls one registration function and no longer imports advisory simulation
path constants, canonical simulation error codes, or problem type prefixes.

The mapper preserves:

1. canonical advisory simulation validation errors as `application/problem+json`,
2. canonical advisory simulation contract-version mismatch handling,
3. canonical advisory simulation execution-failure handling,
4. standard FastAPI validation responses for non-advisory endpoints,
5. existing generic safe 500 handling for other unhandled QCP exceptions.

## Compatibility

No route path, response body contract, OpenAPI schema, database schema, Kafka contract, metric, or
runtime topology changed. This is an in-process design modularity change with behavior-preserving
tests around advisory and non-advisory validation responses.

## Same-Pattern Scan

Reviewed QCP bootstrap and adjacent advisory simulation route tests. The same path-specific
exception mapping pattern was isolated to QCP bootstrap; the advisory route already owned
execution-failure mapping, while validation failures required an app-level registry because request
validation happens before route execution.

## Validation

Focused validation before commit:

1. `python -m pytest tests/integration/services/query_service/test_advisory_simulation_router.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
2. `python -m ruff check src/services/query_control_plane_service/app/main.py src/services/query_control_plane_service/app/exception_mappers.py tests/integration/services/query_service/test_advisory_simulation_router.py`
3. `python -m ruff format --check src/services/query_control_plane_service/app/main.py src/services/query_control_plane_service/app/exception_mappers.py tests/integration/services/query_service/test_advisory_simulation_router.py`
4. `make architecture-guard`
5. QCP runtime import proof with service-local `PYTHONPATH`.

## Guidance Decision

Repository context was updated because the slice adds a reusable rule for exception mapper
placement in QCP and future FastAPI services. No platform skill update was needed; the lesson is
repo-local architecture guidance, not a new cross-repo execution workflow.
