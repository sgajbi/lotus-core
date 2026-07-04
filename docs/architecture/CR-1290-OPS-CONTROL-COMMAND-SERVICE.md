# CR-1290 Ops Control Command Service Boundary

## Scope

Issue cluster: GitHub issue #446.

This slice moves ingestion operations control update validation out of the event replay HTTP router
and into an application-layer command service.

## Objective

Keep `PUT /ingestion/ops/control` responsible for API request binding and HTTP error mapping while
the replay-window ordering rule and service delegation live behind an application command boundary.

## Changes

1. Added `src/services/event_replay_service/app/application/ops_control_commands.py`.
2. Introduced `OpsControlUpdateCommand`, `OpsControlCommandService`, and
   `OpsControlCommandError`.
3. Rewired `PUT /ingestion/ops/control` through a command-service dependency.
4. Added focused command tests for valid update delegation and invalid replay-window rejection.

## Behavior And Compatibility

No route path, HTTP method, status code, request DTO, response DTO, OpenAPI metadata, replay-window
validation rule, update delegation arguments, actor field, or error detail body changed.

The application service uses a plain command dataclass. The router remains responsible for mapping
`IngestionOpsModeUpdateRequest` into that command and translating command errors into FastAPI
`HTTPException`.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\event_replay_service\test_ops_control_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - 6 passed.
2. `python -m pytest tests\unit\services\event_replay_service\test_ops_control_commands.py tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_replay_retry_payloads.py`
   - 40 passed.
3. `python -m ruff check src\services\event_replay_service\app\application\ops_control_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ops_control_commands.py`
   - passed.
4. `python -m ruff format --check src\services\event_replay_service\app\application\ops_control_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ops_control_commands.py`
   - passed.
5. `make architecture-guard`
   - passed.
6. `make quality-wiki-docs-gate`
   - passed.
7. `git diff --check`
   - passed with CRLF normalization warnings only.
8. `python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\ops_control_commands.py -s -a`
   - average complexity `A (1.4285714285714286)`; `update_ingestion_ops_control` is now `A (2)`.
9. `python -m radon raw src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\ops_control_commands.py`
   - router LOC now 1783; ops-control command service LOC is 53.

## Documentation, Wiki, Context, And Skill Decision

No README, wiki, repo context, central context, or skill update is required for this narrow internal
layering slice. Public API and operator-facing behavior are unchanged.

## Remaining Work

Continue issue #446 by extracting remaining read/query response boundaries only when the extraction
removes real ownership coupling rather than just moving one-line service calls.
