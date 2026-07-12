# CR-1426 Ingestion Command Handler Router Boundary

Date: 2026-07-06

## Objective

Fix GitHub issue #532 by moving repeated ingestion command orchestration out of HTTP routers and
behind application command handlers.

## Change

- Added `IngestionPublishCommandHandler` for publish-backed ingestion routes.
- Added `ReferenceDataIngestionCommandHandler` for reference-data persistence routes.
- Converted transaction, portfolio, instrument, market-price, FX-rate, portfolio-bundle,
  reprocessing, and reference-data routers to bind HTTP request data, call command handlers, map
  application exceptions, and shape response DTOs.
- Kept existing business-date command-handler pattern unchanged and aligned the new handlers with
  the same lifecycle semantics.
- Added command-handler tests covering accepted flow, idempotency replay, mode-blocked errors,
  publish/persist failures, queue-bookkeeping failure, and single-record publish behavior.
- Added a router-boundary regression test that blocks reintroducing job creation, request lineage,
  rate-limit enforcement, concrete publish/persist calls, or job failure bookkeeping into converted
  ingestion routers.

## Layering Alignment

This slice aligns the touched ingestion paths to the target backend flow:

1. external consumer
2. API/controller/route
3. request DTO mapper or command construction
4. application use case
5. domain model and domain service
6. port/interface
7. infrastructure adapter
8. database, cache, queue, or external API

The converted routers now sit at the API/controller layer and only bind HTTP input, build command
objects, map application exceptions, and shape DTO responses. The command handlers own the
application use-case flow for write-mode checks, rate limits, idempotency/job lifecycle, publish or
persist execution, failure marking, and queue-bookkeeping. Queue and database effects remain behind
the existing ingestion service, reference-data ingestion service, job service, event publisher, and
repository/store collaborators.

## Expected Improvement

- Reduces design-time complexity by centralizing ingestion lifecycle orchestration in reusable
  application handlers.
- Reduces runtime drift risk because write-mode checks, rate limiting, idempotency replay, failure
  marking, and queue-bookkeeping behavior now use common command-handler paths.
- Makes ingestion behavior testable without FastAPI, Kafka, or database adapters.
- Keeps routers as delivery adapters responsible for request binding, exception-to-HTTP mapping,
  examples, and response DTO shaping.

## Compatibility

No API path, request DTO, response DTO, OpenAPI response status, idempotency replay message,
rate-limit error shape, publish-failure mapping, Kafka topic, database schema, migration, or runtime
deployment topology changed.

Single-transaction ingestion remains jobless as before: it uses write-mode/rate-limit checks and
publishes directly through the command handler without creating ingestion job metadata.

## Validation

- `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_publish_commands.py tests\unit\services\ingestion_service\services\test_reference_data_ingestion_commands.py tests\unit\services\ingestion_service\routers\test_ingestion_router_command_boundaries.py tests\unit\services\ingestion_service\application\test_reference_data_ingestion_registry.py tests\unit\services\ingestion_service\routers\test_job_bookkeeping.py tests\unit\services\ingestion_service\routers\test_publish_errors.py -q`
- Scoped Ruff check and format check for touched command handlers, routers, dependencies, and tests.
- Scoped mypy for touched command handlers, routers, and dependencies.
- Ingestion app import proof with service-local `PYTHONPATH`.
- Static same-pattern scan for forbidden router orchestration fragments in converted routers.

## Documentation Decision

Repo context updated because this changes durable repository-local architecture guidance. No wiki
change is required because public API behavior and operator workflows are unchanged.

No platform skill change is required for this repo-local application-boundary pattern; the
repeatable rule is captured in `REPOSITORY-ENGINEERING-CONTEXT.md`, the static router-boundary
test, and the codebase review ledger.
