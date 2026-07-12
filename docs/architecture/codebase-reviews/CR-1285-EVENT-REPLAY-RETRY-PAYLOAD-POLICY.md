# CR-1285 Event Replay Retry Payload Policy Boundary

## Scope

Issue cluster: GitHub issues #446, #534, and #639.

This slice moves deterministic replay fingerprinting, partial retry payload selection, and replay
record counting out of the event replay HTTP router and into an application-layer helper module.

## Objective

Reduce router-owned replay policy while preserving the existing ingestion retry and consumer-DLQ
replay HTTP contracts.

## Changes

1. Added `src/services/event_replay_service/app/application/replay_retry_payloads.py`.
2. Moved partial retry payload filtering for transactions, portfolios, instruments, business dates,
   and reprocess transaction requests into the application helper.
3. Moved deterministic replay fingerprint construction and replay record-count calculation into the
   application helper.
4. Rewired `ingestion_operations.py` to call the helper instead of owning the policy inline.
5. Moved focused payload-filter tests out of the router test module and added direct application
   tests for payload counting and fingerprint stability.

## Behavior And Compatibility

No route path, HTTP method, status code, response model, OpenAPI metadata, replay audit field,
fingerprint basis, idempotency behavior, Kafka publishing behavior, dry-run behavior, duplicate
blocking behavior, or bookkeeping behavior changed.

This is an in-process design-modularity improvement only. It does not introduce a runtime service
split and does not complete the broader `ReplayCommandService` extraction tracked by #534.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\event_replay_service\test_replay_retry_payloads.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - 34 passed.
2. `make architecture-guard`
   - passed.
3. `python -m ruff check src\services\event_replay_service\app\application\replay_retry_payloads.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_replay_retry_payloads.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - passed.
4. `python -m ruff format --check src\services\event_replay_service\app\application\replay_retry_payloads.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_replay_retry_payloads.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - passed.
5. `python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\replay_retry_payloads.py -s -a`
   - average complexity remained `A (2.015151515151515)`.
6. `python -m radon raw src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\replay_retry_payloads.py`
   - router LOC now 2762; extracted application helper LOC is 131.

## Documentation, Wiki, Context, And Skill Decision

No README, wiki, repo context, central context, or skill update is required for this narrow slice.
The durable learning is already covered by the existing backend delivery, codebase review, and CI
enforcement skills: move repeated router policy into application helpers with focused tests, keep
runtime behavior stable, and record evidence in the review ledger.

## Remaining Work

1. Continue #534 by introducing a replay command service for ingestion retry and consumer-DLQ
   replay workflow orchestration.
2. Continue #446 by extracting more cohesive replay response and DLQ candidate helpers from
   `ingestion_operations.py` with behavior tests.
3. Keep #639 protected through the existing architecture guard that rejects concrete Kafka utility
   imports in event replay routers.
