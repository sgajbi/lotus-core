# CR-1218 Ingestion Publish Dependency Errors

Date: 2026-07-01

## Objective

Continue GitHub issue #594 by mapping Kafka publish dependency failures from generic HTTP 500
responses to a governed HTTP 503 contract with retry guidance.

## Change

- Added shared ingestion publish-error mapping in `routers/publish_errors.py`.
- Migrated direct ingestion publish routers for transactions, portfolios, instruments, market
  prices, FX rates, business dates, portfolio bundle, upload commit, and transaction reprocessing
  to raise the shared 503 response.
- Preserved the existing `INGESTION_PUBLISH_FAILED` application error code and failed-record-key
  payload contract while adding dependency metadata, retryability, `Retry-After`, lineage, publish
  state, and published-record count.
- Updated OpenAPI response examples to document publish failures as named 503 examples alongside
  existing mode-blocked 503 examples.
- Corrected mixed portfolio-bundle partial-publish accounting so records published by completed
  groups contribute to `published_record_count`.

## Expected Improvement

Clients and operators can now distinguish Kafka dependency unavailability from generic server
defects. Retry behavior is explicit, partial publish state is source-safe and machine-readable, and
all direct ingestion publish routers use one mapper instead of duplicated response bodies.

## Tests Added Or Updated

- Unit mapper tests cover dependency metadata, retryability, `Retry-After`, lineage, unpublished
  state, and partial state.
- Portfolio-bundle service coverage now asserts completed group counts are reflected in
  `published_record_count`.
- ASGI ingestion router coverage asserts 503 responses, `Retry-After`, dependency metadata,
  failed-record keys, partial/full publish state, and preserved failure-history behavior.
- Ingestion OpenAPI tests assert publish failures are documented as named 503 examples with
  `Retry-After` header metadata.

## Validation Evidence

- `python -m pytest tests/unit/services/ingestion_service/routers/test_publish_errors.py tests/unit/services/ingestion_service/services/test_ingestion_service.py -q`
  passed with 14 tests.
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
  passed with 30 tests.
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
  passed with 214 tests.
- Scoped Ruff lint passed for the touched ingestion routers, mapper, service, and tests.
- Scoped Ruff format check passed for the touched ingestion routers, mapper, service, and tests.
- `make lint` passed, including the ingestion contract gate and QCP problem-details guard.
- `make openapi-gate`, `make api-vocabulary-gate`, and `make quality-openapi-spectral-gate`
  passed; the Spectral gate generated 14 service OpenAPI artifacts with no warn-or-higher results.
- `make typecheck` passed with no issues in 50 source files.
- `make quality-unit-collection-gate` collected 3257/3267 unit-lane tests with 10 deselected.
- `make quality-wiki-docs-gate` and `git diff --check` passed.

## Downstream Compatibility

Route paths, request DTOs, success DTOs, ingestion job persistence, failure-history persistence,
Kafka publish attempts, idempotency replay behavior, and `INGESTION_PUBLISH_FAILED` application
code are preserved. The intentional behavior change is the HTTP status and response metadata for
Kafka publish dependency failures: they now return HTTP 503 with `Retry-After` instead of HTTP 500.
Reference-data persistence failures and post-publish bookkeeping failures remain distinct 500
contracts.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, repository context, and quality/refactor
scorecards were updated. No wiki update is required because no operator command, runbook, or
published workflow changed.

## Remaining Follow-Up

- Consider a later dependency-error mapper for event-replay publish/replay routes, which use a
  separate control-plane surface and recovery model.
- Keep issue #594 open for PR/CI/QA evidence until the branch is merged and validated.
