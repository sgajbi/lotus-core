# CR-1288 Replay Command Error Boundary

## Scope

Issue cluster: GitHub issues #446 and #534.

This slice extracts the shared replay command error type out of the ingestion retry command module.

## Objective

Prevent consumer DLQ replay command code from depending on an ingestion-retry-specific module for a
generic replay command error.

## Changes

1. Added `src/services/event_replay_service/app/application/replay_command_errors.py`.
2. Moved `ReplayCommandError` into the shared application module.
3. Rewired ingestion retry and consumer DLQ replay command services to import the shared error.

## Behavior And Compatibility

No route path, HTTP method, status code, request DTO, response DTO, OpenAPI metadata, problem-detail
body, replay audit field, publish side effect, or bookkeeping behavior changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\unit\services\event_replay_service\test_replay_retry_payloads.py`
   - 36 passed.
2. `python -m ruff check src\services\event_replay_service\app\application\replay_command_errors.py src\services\event_replay_service\app\application\ingestion_retry_commands.py src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py`
   - passed.
3. `python -m ruff format src\services\event_replay_service\app\application\replay_command_errors.py src\services\event_replay_service\app\application\ingestion_retry_commands.py src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py`
   - 6 files left unchanged.
4. `make architecture-guard`
   - passed.
5. `make quality-wiki-docs-gate`
   - passed.
6. `git diff --check`
   - passed with CRLF normalization warnings only.

## Documentation, Wiki, Context, And Skill Decision

No README, wiki, repo context, central context, or skill update is required. This is a narrow
internal dependency cleanup that preserves public API and operator-facing behavior.
