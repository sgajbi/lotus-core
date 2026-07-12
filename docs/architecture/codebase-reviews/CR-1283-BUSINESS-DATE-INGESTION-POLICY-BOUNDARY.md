# CR-1283 Business Date Ingestion Policy Boundary

- Date: 2026-07-04
- Scope: ingestion business-date API router boundary
- GitHub issue: #635

## Objective

Remove the final API-router boundary exception by moving business-date validation policy and
business-calendar repository wiring out of the ingestion router.

## Expected Improvement

`src/services/ingestion_service/app/routers/business_dates.py` no longer imports a repository or
injects repository providers directly. The router now maps HTTP requests and errors, while
`BusinessDateIngestionPolicy` owns payload, future-date, and monotonic-advance validation.
`src/services/ingestion_service/app/dependencies.py` owns the FastAPI composition from database
session to repository to validation policy.

This clears the local #635 API-router boundary exception and leaves
`docs/standards/api-layer-router-boundary-exceptions.json` empty. The guard remains the reusable
platform pattern: future router repository, database-session, SQLAlchemy-operation, external-client,
or file-access coupling must either be fixed or explicitly registered as transitional debt.

## Tests Added Or Updated

Added focused policy coverage:

1. `tests/unit/services/ingestion_service/services/test_business_date_ingestion_policy.py`

Updated ingestion route tests to override the dependency composition provider instead of a
router-local repository provider:

1. `tests/integration/services/ingestion_service/test_ingestion_routers.py`

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/unit/services/ingestion_service/services/test_business_date_ingestion_policy.py tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
   passed with 222 tests.
2. `make architecture-guard` passed with an empty API-router boundary exception registry.
3. `python -m json.tool docs/standards/api-layer-router-boundary-exceptions.json` passed.
4. Scoped Ruff lint and format checks passed for the ingestion dependency module, repository,
   policy service, router, and tests.
5. `make lint` passed.
6. `make quality-wiki-docs-gate` passed.
7. `make typecheck` passed.
8. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, request body, response DTO, OpenAPI output, Kafka topic, idempotency
behavior, ingestion job behavior, repository query, future-date policy, monotonic policy, publish
failure behavior, or canonical error body changed. The intentional change is internal validation
and dependency-composition ownership.

## Documentation Updates

Updated the codebase review ledger and repository context. No wiki update is required because this
slice changes internal architecture and validation evidence, not consumer-facing or operator-facing
wiki truth.
