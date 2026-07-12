# CR-1295 Ingestion Job Lifecycle Fencing

## Scope

Issue cluster: GitHub issue #701.

This slice adds expected-state guards to ingestion job lifecycle mutations and makes replay-success
bookkeeping atomic so recovery commands cannot silently overwrite concurrent job state.

## Objective

Reduce runtime race risk and operator-truth ambiguity in ingestion job state transitions. Recovery
commands should not advance retry counters, move jobs to queued, or repair bookkeeping from stale
reads when another worker or operator path has changed the row.

## Changes

1. Added expected-status predicates to `mark_job_queued(...)`, `mark_job_failed(...)`, and
   `mark_job_retried(...)`; each mutation now returns a boolean update outcome.
2. Added `mark_job_retried_and_queued(...)` as a single atomic retry-success transition that
   increments retry metadata and moves the job to `queued` in one update.
3. Exposed the guarded transition outcomes through `IngestionJobService`.
4. Rewired ingestion-job retry and consumer-DLQ replay success bookkeeping to use the atomic
   transition and return governed `409` conflict details when the expected state is stale.
5. Rewired bookkeeping repair to treat a stale accepted-to-queued repair as a governed conflict
   instead of reporting success.
6. Added focused lifecycle, retry, consumer-DLQ, and repair tests for expected-status SQL,
   accepted-to-queued success, stale update rejection, atomic retry+queued behavior, and
   replay/repair conflict responses.

## Behavior And Compatibility

Normal successful ingestion, retry, consumer-DLQ replay, failure recording, replay-audit, and
bookkeeping-repair behavior is unchanged when the job is in the expected state.

Intentional race-case behavior changes:

- stale queued transitions now return `False` at the service boundary,
- replay success returns governed conflict details if the job state changed before bookkeeping,
- bookkeeping repair returns a governed conflict if an accepted job changed before repair.

Route paths, request DTOs, success DTOs, Kafka topics, replay fingerprints, replay audit schema,
and database schema are unchanged.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py`
   - 33 passed.
2. `python -m ruff check src\services\ingestion_service\app\services\ingestion_job_lifecycle.py src\services\ingestion_service\app\services\ingestion_job_service.py src\services\event_replay_service\app\application\ingestion_retry_commands.py src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py src\services\event_replay_service\app\application\bookkeeping_repair_commands.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py`
   - passed.
3. `python -m ruff format --check src\services\ingestion_service\app\services\ingestion_job_lifecycle.py src\services\ingestion_service\app\services\ingestion_job_service.py src\services\event_replay_service\app\application\ingestion_retry_commands.py src\services\event_replay_service\app\application\consumer_dlq_replay_commands.py src\services\event_replay_service\app\application\bookkeeping_repair_commands.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py`
   - passed.
4. `make quality-wiki-docs-gate`
   - passed.
5. `python C:\Users\Sandeep\.codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki`
   - passed.
6. `git diff --check`
   - passed with CRLF normalization warnings only.
7. `powershell -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
   - reported expected pre-merge published-wiki drift for authored pages including
     `Event-Replay-Service.md` and `Ingestion-Service.md`; publish after merge remains required.

## Documentation, Wiki, Context, And Skill Decision

Updated repo context plus Ingestion Service and Event Replay wiki source with the guarded lifecycle
transition rule.

No central Lotus skill change is required. The existing backend delivery and codebase review ledger
guidance already requires issue-driven adjacent-pattern scans and explicit design-vs-runtime
complexity reduction evidence.

## Remaining Work

Broader follow-up can migrate direct ingestion routers to react to false lifecycle outcomes where a
client-visible conflict is useful. This slice focuses on the issue-identified replay, repair, and
late-failure race risks without changing normal ingestion success contracts.
