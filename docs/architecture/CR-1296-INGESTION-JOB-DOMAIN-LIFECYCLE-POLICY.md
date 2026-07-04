# CR-1296 Ingestion Job Domain Lifecycle Policy

## Scope

Issue cluster: GitHub issue #659.

This slice establishes the first pure domain lifecycle policy for ingestion jobs and adds the
repository standard that future workflow state machines must follow.

## Objective

Reduce design-time complexity and status-string drift by moving ingestion job lifecycle vocabulary,
allowed transitions, retry metadata requirements, replay-audit requirements, failure-evidence
requirements, and terminal-state posture out of persistence helpers and into a pure domain policy.

## Changes

1. Added `src/services/ingestion_service/app/domain/ingestion_job_lifecycle_policy.py` with
   ingestion job statuses, named transitions, transition rules, expected source statuses, target
   statuses, and audit/evidence metadata flags.
2. Added direct domain-policy tests for known statuses, valid transitions, invalid source states,
   retry metadata requirements, replay-audit requirements, failure-evidence requirements, and
   explicit terminal-state posture.
3. Rewired ingestion job lifecycle persistence helpers to consume policy-derived expected statuses
   and status values instead of owning local status-string sets.
4. Added `docs/standards/domain-state-transition-policy.md` as the reusable domain lifecycle
   standard for future workflows.
5. Updated repo context and the Ingestion Service wiki source with the durable domain-policy rule.

## Behavior And Compatibility

This is a design-modularity slice inside the existing deployable application. It is not a runtime
service split.

No route path, request DTO, response DTO, Kafka topic, database schema, status value, replay audit
schema, or lifecycle mutation behavior changed. The policy preserves the guarded lifecycle
behavior introduced in CR-1295 while moving the transition rules to a pure domain layer.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\ingestion_service\domain\test_ingestion_job_lifecycle_policy.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py tests\unit\services\event_replay_service\test_ingestion_retry_commands.py tests\unit\services\event_replay_service\test_consumer_dlq_replay_commands.py tests\unit\services\event_replay_service\test_bookkeeping_repair_commands.py`
   - 38 passed.
2. `python -m ruff check src\services\ingestion_service\app\domain\ingestion_job_lifecycle_policy.py src\services\ingestion_service\app\domain\__init__.py src\services\ingestion_service\app\services\ingestion_job_lifecycle.py src\services\ingestion_service\app\services\ingestion_job_service.py tests\unit\services\ingestion_service\domain\test_ingestion_job_lifecycle_policy.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py`
   - passed.
3. `python -m ruff format --check src\services\ingestion_service\app\domain\ingestion_job_lifecycle_policy.py src\services\ingestion_service\app\domain\__init__.py src\services\ingestion_service\app\services\ingestion_job_lifecycle.py src\services\ingestion_service\app\services\ingestion_job_service.py tests\unit\services\ingestion_service\domain\test_ingestion_job_lifecycle_policy.py tests\unit\services\ingestion_service\services\test_ingestion_job_service_state_transitions.py`
   - passed.
4. `make quality-wiki-docs-gate`
   - passed.
5. `python C:\Users\Sandeep\.codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki`
   - passed.
6. `git diff --check`
   - passed with CRLF normalization warnings only.
7. `powershell -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
   - reported expected pre-merge published-wiki drift for authored pages including
     `Ingestion-Service.md`; publish after merge remains required.

## Documentation, Wiki, Context, And Skill Decision

Updated repo context, Ingestion Service wiki source, and repository domain state-transition
standard.

No central Lotus skill change is required. The existing backend delivery and codebase review ledger
guidance already routes lifecycle policy extraction through repo delivery governance plus the
codebase review ledger.

## Remaining Work

Issue #659 remains broader than ingestion jobs. Future slices should apply the same standard to
reconciliation run lifecycle, valuation/aggregation job lifecycle, simulation session lifecycle,
and transaction booking/correction/restatement lifecycle.
