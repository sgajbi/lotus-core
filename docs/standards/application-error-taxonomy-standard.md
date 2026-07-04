# Application Error Taxonomy Standard

Application services should raise framework-independent application errors. API routers, workers,
consumers, and operator entrypoints own transport-specific mapping.

## Required Pattern

1. Application and domain logic must not raise FastAPI, Starlette, or other HTTP framework
   exceptions.
2. Application errors must carry a stable `reason_code`, source-safe `detail`, and explicit
   retryability where useful.
3. API routers map application errors to HTTP status codes, headers, and response detail bodies.
4. Worker and consumer entrypoints map application errors to retry, reject, DLQ, recovery, or
   operator-attention outcomes without depending on HTTP status vocabulary.
5. Tests should cover both the framework-independent application failure and at least one transport
   mapping for API-facing paths.

## Current Representative Workflow

The ingestion upload use case is the first representative path:

1. `src/services/ingestion_service/app/application/errors.py` defines `ApplicationError`,
   `ValidationRejected`, and `UnsupportedOperation`.
2. `UploadIngestionService` raises those application errors for unsupported upload formats,
   invalid CSV/XLSX content, empty uploads, rejected partial uploads, and uploads with no valid
   rows.
3. `src/services/ingestion_service/app/routers/uploads.py` maps upload application error
   `reason_code` values to the existing HTTP 400 or 422 behavior and preserves existing response
   `detail` shapes.
4. The FastAPI dependency provider for `UploadIngestionService` lives in the router module, not the
   application service module.

## Enforcement

`make architecture-guard` runs `scripts/application_error_taxonomy_guard.py`. The guard protects
the representative upload application service from reintroducing FastAPI imports,
`HTTPException`, or HTTP status mapping.

## Runtime Boundary

This standard is an in-process application/API boundary. It does not create a new runtime service,
queue, database, endpoint, or deployment topology.

