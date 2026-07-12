# CR-1287 Consumer DLQ Replay Command Service Boundary

## Scope

Issue cluster: GitHub issues #446 and #534.

This slice moves consumer DLQ replay orchestration out of the event replay HTTP router and into an
application-layer command service.

## Objective

Reduce router-owned recovery workflow complexity while preserving the existing consumer DLQ replay
API contract and operator diagnostics.

## Changes

1. Added `src/services/event_replay_service/app/application/consumer_dlq_replay_commands.py`.
2. Introduced DTO-free command/result dataclasses for consumer DLQ replay.
3. Rewired `POST /ingestion/dlq/consumer-events/{event_id}/replay` through
   `ConsumerDlqReplayCommandService`.
4. Removed consumer DLQ replay candidate, not-replayable, duplicate, publish, bookkeeping, and
   mandatory-audit helpers from `ingestion_operations.py`.
5. Moved consumer DLQ replay tests into
   `tests/unit/services/event_replay_service/test_consumer_dlq_replay_commands.py`.

## Behavior And Compatibility

No route path, HTTP method, status code, request DTO, response DTO, OpenAPI metadata, replay audit
field, deterministic fingerprint basis, missing-correlation diagnostics, duplicate-blocking
behavior, dry-run behavior, publish side effect, or post-publish bookkeeping behavior changed.

The application service returns a plain command result. The router remains responsible for mapping
that result into the public `ConsumerDlqReplayResponse` DTO and for translating command errors into
FastAPI `HTTPException`.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_replay_retry_payloads.py`
   - 36 passed.
2. `python -m ruff check src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - passed.
3. `python -m ruff format --check src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - passed.
4. `make architecture-guard`
   - passed.
5. `make quality-wiki-docs-gate`
   - passed.
6. `git diff --check`
   - passed with CRLF normalization warnings only.
7. `python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\ingestion_retry_commands.py src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py -s -a`
   - average complexity `A (1.8714285714285714)`.
8. `python -m radon raw src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\ingestion_retry_commands.py src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py`
   - router LOC now 1888; ingestion retry command service LOC is 490; consumer DLQ command
     service LOC is 533.

## Documentation, Wiki, Context, And Skill Decision

No README, wiki, repo context, central context, or skill update is required for this narrow internal
layering slice. Public API and operator-facing behavior are unchanged. The durable learning remains
issue-backed: keep recovery workflow orchestration in application services, keep routers thin, and
use plain command/result shapes before mapping public DTOs at the API edge.

## Remaining Work

1. Continue #446 by extracting remaining ingestion operations response and bookkeeping helpers when
   they form cohesive application-use-case slices.
2. Keep #639 protected through architecture guard coverage against concrete Kafka utility imports in
   event replay routers.
3. Review the event replay command services for a future shared replay-audit port once additional
   recovery paths are extracted.
