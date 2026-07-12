# CR-1286 Ingestion Retry Command Service Boundary

## Scope

Issue cluster: GitHub issues #446 and #534.

This slice moves ingestion-job retry workflow orchestration out of the event replay HTTP router and
into an application-layer command service. Consumer DLQ replay remains router-owned for the next
bounded extraction slice.

## Objective

Reduce runtime and design-time complexity in `ingestion_operations.py` by keeping FastAPI routing
responsible for request binding and HTTP error mapping only, while retry authorization, deterministic
fingerprinting, duplicate blocking, replay publishing, replay audit persistence, and post-publish
bookkeeping live behind an application command boundary.

## Changes

1. Added `src/services/event_replay_service/app/application/ingestion_retry_commands.py`.
2. Introduced `IngestionRetryCommandService` and `ReplayCommandError`.
3. Rewired `POST /ingestion/jobs/{job_id}/retry` to depend on the command service and map command
   errors to existing HTTP responses.
4. Removed ingestion-job retry workflow helpers from `ingestion_operations.py`.
5. Moved retry workflow tests into
   `tests/unit/services/event_replay_service/test_ingestion_retry_commands.py` and added a full
   dry-run orchestration test.

## Behavior And Compatibility

No route path, HTTP method, status code, request DTO, response model, OpenAPI metadata, replay audit
field, deterministic fingerprint basis, idempotency behavior, dry-run behavior, duplicate-blocking
behavior, publish side effect, failed-job side effect, or post-publish bookkeeping behavior changed.

The application service intentionally uses a transport-neutral command error that carries the same
status code and problem-detail body the router returned before. The router remains responsible for
turning that command error into FastAPI `HTTPException`.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\unit\services\event_replay_service\test_replay_retry_payloads.py`
   - 35 passed.
2. `make architecture-guard`
   - passed.
3. `python -m ruff check src\services\event_replay_service\app\application\ingestion_retry_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - passed.
4. `python -m ruff format --check src\services\event_replay_service\app\application\ingestion_retry_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - passed.
5. `make quality-wiki-docs-gate`
   - passed.
6. `git diff --check`
   - passed with CRLF normalization warnings only.
7. `python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\ingestion_retry_commands.py -s -a`
   - average complexity `A (1.921875)`.
8. `python -m radon raw src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\ingestion_retry_commands.py`
   - router LOC now 2437; extracted command service LOC is 490.

## Documentation, Wiki, Context, And Skill Decision

No README, wiki, repo context, central context, or skill update is required for this narrow internal
layering slice. Public API and operator-facing behavior are unchanged. The durable learning is the
same issue-backed pattern already being applied in this branch: repeated router-owned recovery
workflow should move into application services with focused tests before broader endpoint or
runtime changes are attempted.

## Remaining Work

1. Continue #534 by extracting consumer DLQ replay orchestration behind a command service.
2. Continue #446 by moving response/candidate assembly out of `ingestion_operations.py` after the
   command boundary is established.
3. Keep #639 protected through the existing architecture guard that rejects concrete Kafka utility
   imports in event replay routers.
