# CR-1385 Reference Data Ingestion Registry

- Date: 2026-07-06
- Status: Hardened locally
- GitHub issue: #540
- Control taxonomy: architecture, mapping anti-corruption, ingestion supportability, testability

## Objective

Move reference-data family dispatch out of FastAPI router functions and into a typed application
registry while preserving every existing ingestion route, DTO, ACK, idempotency, and persistence
contract.

## Finding

`ingestion_service/app/routers/reference_data.py` encoded each reference-data endpoint's entity
type, accepted-count calculation, DTO-to-record `model_dump()` transformation, and
`ReferenceDataIngestionService.upsert_*` method call as a route-local lambda. That made the router
own application command mapping and encouraged copy/paste orchestration for every new
reference-data family.

## Change

Added `ReferenceDataIngestionRegistry` in
`ingestion_service/app/application/reference_data_ingestion_registry.py`. The registry owns the
command key, endpoint, entity type, payload record attribute, and persistence method name for each
reference-data family.

The router now resolves a command key and delegates accepted-count, request-payload serialization,
record extraction, and persistence dispatch to the registry. The shared route handler still owns
HTTP concerns: idempotency key resolution, write-mode checks, rate limiting, job creation/replay,
failure mapping, and ACK construction.

## Compatibility

No route path, request DTO, success DTO, idempotency behavior, persistence service method,
database schema, Kafka contract, OpenAPI route registration, metric, or runtime topology changed.
Record persistence still uses each record's existing `model_dump()` behavior, and request payload
evidence still uses payload `model_dump(mode="json")`.

## Same-Pattern Scan

Scanned `reference_data.py` for route-local `persist_fn`, `lambda: reference_data_service`,
`upsert_*`, endpoint/entity mapping, accepted-count mapping, and request-payload mapping. The
reference-data router no longer contains persistence method dispatch. Adjacent ingestion router
orchestration remains issue-backed backlog and should use application command handlers or registries
instead of new router-local lambdas.

## Validation

Focused validation before commit:

1. `python -m pytest tests/unit/services/ingestion_service/application/test_reference_data_ingestion_registry.py -q`
2. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests/integration/services/ingestion_service/test_ingestion_routers.py::test_reference_data_ingestion_replays_duplicate_idempotency_key tests/integration/services/ingestion_service/test_ingestion_routers.py::test_reference_data_ingestion_marks_job_failed_when_persist_fn_raises -q`
3. Scoped Ruff check/format on changed source, tests, and documentation.
4. `make architecture-guard`
5. `make quality-wiki-docs-gate`

## Guidance Decision

Repository context was updated because the slice adds a reusable `lotus-core` ingestion rule:
family-to-persistence dispatch belongs in `app/application`, not FastAPI route lambdas. No platform
skill update was needed; the broader skill already requires a guidance review, and this lesson is a
repo-local architecture boundary. No wiki update was required because no operator-facing behavior or
public repository navigation changed.
