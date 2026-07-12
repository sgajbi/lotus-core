# CR-1292 Ingestion Operations Example Catalog

## Scope

Issue cluster: GitHub issue #446.

This slice moves the ingestion operations OpenAPI/operator example catalog out of the large
event-replay route module and into a dedicated router-support module.

## Objective

Reduce review cost in `routers/ingestion_operations.py` without changing route behavior by keeping
API documentation data close to the router package but outside the main route implementation.

## Changes

1. Added `src/services/event_replay_service/app/routers/ingestion_operations_examples.py`.
2. Moved 34 `*_EXAMPLE` and `*_EXAMPLES` constants out of
   `routers/ingestion_operations.py`.
3. Added `INGESTION_OPERATION_EXAMPLES` as a registry for guard tests and future example audits.
4. Added focused tests proving the example catalog is JSON-serializable and the main router no
   longer owns top-level example assignments.
5. Updated repo context and the Event Replay wiki page with the durable example-catalog placement
   rule.

## Behavior And Compatibility

No route path, HTTP method, status code, query parameter, request body, response DTO, OpenAPI
example value, database query, replay behavior, DLQ behavior, audit behavior, health response, or
operator-facing error body changed.

This is design modularity only. It does not create a new runtime boundary.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations_examples.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations_queries.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py`
   - 31 passed.
2. `python -m ruff check src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\routers\ingestion_operations_examples.py tests\unit\services\event_replay_service\test_ingestion_operations_examples.py`
   - passed.
3. `python -m ruff format --check src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\routers\ingestion_operations_examples.py tests\unit\services\event_replay_service\test_ingestion_operations_examples.py`
   - passed.
4. `make architecture-guard`
   - passed.
5. `$env:PYTHONPATH = "src/services/event_replay_service;src/libs/portfolio-common"; python -c "import app.main"`
   - passed.
6. `rg -n "^([A-Z0-9_]+_EXAMPLE|[A-Z0-9_]+_EXAMPLES) =" src\services\event_replay_service\app\routers\ingestion_operations.py`
   - no matches.
7. `python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\routers\ingestion_operations_examples.py -s -a`
   - average complexity `A (1.32)` for the router.
8. `python -m radon raw src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\routers\ingestion_operations_examples.py`
   - router LOC now 1227; example-catalog LOC 606.

## Documentation, Wiki, Context, And Skill Decision

Repo context and `wiki/Event-Replay-Service.md` changed because this slice establishes durable
structure guidance for OpenAPI/operator examples in the event-replay service.

No README, central context, or skill update is required. The existing backend and README/wiki
governance skills already cover the pattern.

## Remaining Work

Continue high-throughput issue work by moving to the next open issue family. For issue #446, the
remaining `ingestion_operations.py` route functions are low-complexity HTTP adapters; further
extraction should only happen when it removes cohesive ownership, not when it merely moves
pass-through service calls.
