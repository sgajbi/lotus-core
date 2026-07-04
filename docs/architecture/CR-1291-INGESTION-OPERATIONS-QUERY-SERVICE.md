# CR-1291 Ingestion Operations Query Service Boundary

## Scope

Issue cluster: GitHub issues #446 and #534.

This slice moves ingestion operations read-side envelope and not-found policy behind an
application-layer query service, and moves event replay command/query composition out of the router.

## Objective

Keep ingestion operations routes responsible for HTTP request binding, API DTO construction, and
FastAPI error mapping while application query behavior owns list totals, missing-resource codes,
and delegation to the ingestion job service.

## Changes

1. Added `src/services/event_replay_service/app/application/ingestion_operations_queries.py`.
2. Introduced `IngestionOperationsQueryService` with plain page/result objects and a not-found
   error carrying code/message only.
3. Added `src/services/event_replay_service/app/dependencies.py` and moved event replay
   command/query dependency composition out of `routers/ingestion_operations.py`.
4. Rewired ingestion job list/failure/record, consumer DLQ list, and replay audit list/get routes
   through the query service.
5. Added focused query-service tests for pagination totals, filter delegation, and governed
   not-found codes.

## Behavior And Compatibility

No route path, HTTP method, status code, query parameter, request body, response DTO, OpenAPI
metadata, database query, consumer DLQ filter, replay audit filter, pagination cursor, total-count
semantics, or existing not-found error body changed.

The query service uses plain dataclasses and code/message errors. The router remains responsible for
mapping those results to API DTOs and `HTTPException`.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations_queries.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py tests\unit\services\event_replay_service\test_ops_control_commands.py`
   - 37 passed.
2. `python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations_queries.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_replay_retry_payloads.py`
   - 39 passed.
3. `python -m ruff check src\services\event_replay_service\app\dependencies.py src\services\event_replay_service\app\application\ingestion_operations_queries.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations_queries.py`
   - passed.
4. `python -m ruff format --check src\services\event_replay_service\app\dependencies.py src\services\event_replay_service\app\application\ingestion_operations_queries.py src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations_queries.py`
   - passed.
5. `make architecture-guard`
   - passed.
6. `make quality-wiki-docs-gate`
   - passed.
7. `python C:\Users\Sandeep\.codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki`
   - passed after replacing a legacy scratch term in `wiki/Security-and-Governance.md`.
8. `python -m pytest tests\unit\docs\test_source_data_product_boundaries.py tests\unit\test_ci_workflow_action_versions.py`
   - 33 passed.
9. `powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
   - reported expected pre-merge publication drift for authored wiki source:
     `API-Surface.md`, `Architecture.md`, `Event-Replay-Service.md`, `Home.md`,
     `Security-and-Governance.md`, and `_Sidebar.md`.
10. `$env:PYTHONPATH = "src/services/event_replay_service;src/libs/portfolio-common"; python -c "import app.main"`
   - passed.
11. `rg -n "KafkaProducer|get_kafka_producer|_ReplayPayloadPublisher|_publish_ingestion_job_retry|_publish_consumer_dlq_replay|_mark_ingestion_job_retry_replayed|_mark_consumer_dlq_replay_replayed|filter_payload_by_record_keys|deterministic_replay_fingerprint|payload_record_count" src\services\event_replay_service\app\routers\ingestion_operations.py`
   - no matches.
12. `git diff --check`
   - passed with CRLF normalization warnings only.
13. `python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\dependencies.py src\services\event_replay_service\app\application\ingestion_operations_queries.py -s -a`
    - average complexity `A (1.2666666666666666)`.
14. `python -m radon raw src\services\event_replay_service\app\routers\ingestion_operations.py src\services\event_replay_service\app\dependencies.py src\services\event_replay_service\app\application\ingestion_operations_queries.py`
    - router LOC now 1753, event replay dependency module LOC 64, query service LOC 132.

## Documentation, Wiki, Context, And Skill Decision

README, repo-local engineering context, and repo-local wiki source were updated because the slice
changed durable structure guidance for event replay:

1. `README.md` now carries a clearer service profile, ecosystem role, data-mesh posture,
   architecture flow, and repository layout table.
2. `REPOSITORY-ENGINEERING-CONTEXT.md` now records the event-replay router/application/dependency
   pattern so future agents do not reintroduce router-owned workflow or composition.
3. `wiki/Home.md`, `wiki/_Sidebar.md`, `wiki/Architecture.md`, and
   `wiki/Event-Replay-Service.md` now expose current-state evidence standards, module structure,
   and extension rules.

No central context or skill update is required: the existing Lotus README/wiki governance skill and
backend delivery guidance already cover the pattern. Public API and operator-facing behavior are
unchanged.

## Remaining Work

Issue #534 is locally clear by code audit and focused tests: the router no longer builds replay
publish payloads, owns replay fingerprint/payload filtering, or calls Kafka producer methods
directly. Continue issue #446 on remaining read/diagnostic endpoints only where a cohesive service
boundary reduces router ownership rather than moving pass-through calls.
