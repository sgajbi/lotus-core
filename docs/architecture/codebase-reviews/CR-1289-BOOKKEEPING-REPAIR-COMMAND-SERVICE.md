# CR-1289 Bookkeeping Repair Command Service Boundary

## Scope

Issue cluster: GitHub issues #446 and #595.

This slice moves post-publish ingestion job bookkeeping repair orchestration out of the event replay
HTTP router and into an application-layer command service.

## Objective

Reduce `ingestion_operations.py` workflow complexity while preserving the governed repair endpoint
contract added for post-publish bookkeeping failures.

## Changes

1. Added `src/services/event_replay_service/app/application/bookkeeping_repair_commands.py`.
2. Introduced `BookkeepingRepairCommandService`, `BookkeepingRepairResult`, and
   `BookkeepingRepairCommandError`.
3. Rewired `POST /ingestion/jobs/{job_id}/bookkeeping/repair` through the command-service
   dependency.
4. Removed route-local repair eligibility, queueing, and response assembly helpers.
5. Moved bookkeeping repair behavior tests into
   `tests/unit/services/event_replay_service/test_bookkeeping_repair_commands.py`.

## Behavior And Compatibility

No route path, HTTP method, status code, request shape, response DTO, OpenAPI metadata, repair
eligibility rule, failure evidence rule, `mark_queued` side effect, recovery action,
supportability reason code, retry-safety flag, or error body changed.

The command service returns a plain repair result. The router remains responsible for mapping that
result into `IngestionJobBookkeepingRepairResponse` and translating command errors into FastAPI
`HTTPException`.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - 10 passed.
2. `python -m pytest tests\unit\services\event_replay_service`
   - 38 passed.
3. `python -m ruff check src\services\event_replay_service\app\application\bookkeeping_repair_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - passed.
4. `python -m ruff format --check src\services\event_replay_service\app\application\bookkeeping_repair_commands.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py tests\unit\services\event_replay_service\test_ingestion_operations.py`
   - passed.
5. `make architecture-guard`
   - passed.
6. `make quality-wiki-docs-gate`
   - passed.
7. `git diff --check`
   - passed with CRLF normalization warnings only.
8. `python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\bookkeeping_repair_commands.py -s -a`
   - average complexity `A (1.575)`.
9. `python -m radon raw src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\application\bookkeeping_repair_commands.py`
   - router LOC now 1779; extracted command-service LOC is 158.

## Documentation, Wiki, Context, And Skill Decision

No README, wiki, repo context, central context, or skill update is required for this narrow internal
layering slice. Public API and operator-facing behavior are unchanged.

## Remaining Work

1. Continue #446 by extracting remaining ingestion operations helper clusters when they are cohesive
   use-case or query-service boundaries.
2. Keep replay and repair command services on plain result shapes with DTO mapping at the API edge.
