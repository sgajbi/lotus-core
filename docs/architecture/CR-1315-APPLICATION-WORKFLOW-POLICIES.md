# CR-1315 Application Workflow Policies

## Scope

Issue cluster: GitHub issue #644.

This slice introduces reusable application workflow policies for representative ingestion
idempotency and replay-audit behavior.

## Objective

Stop treating idempotency, command context, correlation lineage, and mandatory replay audit as
one-off parameter plumbing in the ingestion job service. Make the reusable workflow boundary
explicit while preserving existing router and downstream contracts.

## Changes

1. Added `src/services/ingestion_service/app/application/workflow_policies.py`.
2. Added `CorrelationContext` and `ApplicationCommandEnvelope`.
3. Added `IdempotencyWorkflow` over `IngestionJobStore`.
4. Added `AuditWorkflow` over `ReplayAuditStore`.
5. Routed `IngestionJobService.create_or_get_job(...)` through `IdempotencyWorkflow`.
6. Routed `IngestionJobService.record_consumer_dlq_replay_audit(...)` through `AuditWorkflow`.
7. Added fake-port workflow tests for duplicate idempotency, conflict outcome, audit success, and
   fail-closed audit errors.
8. Added `scripts/application_workflow_policy_guard.py` and wired it into
   `make architecture-guard`.
9. Added `docs/standards/application-workflow-policy-standard.md`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema,
ingestion job idempotency behavior, replay-audit behavior, replay-audit error behavior, Kafka
topic, event payload, metric name, runtime composition, or deployment topology changed.

Existing routers can continue calling `IngestionJobService.create_or_get_job(...)` and
`record_consumer_dlq_replay_audit(...)` with the same arguments.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_application_workflow_policy_guard.py tests/unit/services/ingestion_service/application/test_workflow_policies.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_ports.py -q`
2. `python scripts/application_workflow_policy_guard.py`
3. Scoped Ruff lint and format checks for the new workflow, guard, and tests.
4. `make architecture-guard`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal application workflow governance, not
operator-facing commands, route behavior, supported features, or published wiki truth.

No new platform skill source change is required in this slice because the existing backend delivery
guidance already directs repeated workflow coupling issues toward ports, fake-port tests, guards,
and context.

## Remaining Work

GitHub issue #644 is locally fixed for representative idempotency/audit workflow acceptance pending
PR CI/QA and issue closure.

Broader command-handler extraction from routers, command behavior certification, and concurrency
coverage across replay, reconciliation, and long-running operations remain follow-up issue scope.
