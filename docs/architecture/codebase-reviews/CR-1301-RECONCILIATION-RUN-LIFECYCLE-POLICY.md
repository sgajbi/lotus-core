# CR-1301 Reconciliation Run Lifecycle Policy

## Scope

Issue cluster: GitHub issue #659.

This slice adds a second governed lifecycle policy for financial reconciliation runs, complementing
the ingestion job lifecycle policy from CR-1296.

## Objective

Move reconciliation run status vocabulary, terminal/retryable classification, completion
transition metadata, and automatic-bundle outcome policy out of service string checks and into a
pure domain policy module.

## Changes

1. Added `financial_reconciliation_service.app.domain.reconciliation_run_lifecycle_policy`.
2. Defined reconciliation run statuses: `RUNNING`, `COMPLETED`, `REQUIRES_REPLAY`, and `FAILED`.
3. Defined the `complete_reconciliation_run` transition with source status, target status, summary
   requirement, and persisted-findings requirement.
4. Moved automatic bundle outcome decisioning for failed runs and error-finding replay posture into
   the domain policy.
5. Rewired reconciliation repository run creation and service completion paths through lifecycle
   policy helpers.
6. Added direct domain tests for transition metadata, valid terminal states, retryable states,
   failed-run escalation, replay-required error findings, and unknown-status handling.

## Behavior And Compatibility

This is a design-modularity slice inside the existing financial reconciliation deployable. It is
not a runtime service split.

No route path, request DTO, response DTO, OpenAPI metadata, repository method signature, database
schema, stored status value, summary field, finding field, automatic-bundle outcome value, metric
name, metric label value, dedupe key, or correlation behavior changed.

## Validation Evidence

Focused local validation before docs update:

1. `python -m pytest tests\unit\services\financial_reconciliation_service\domain\test_reconciliation_run_lifecycle_policy.py tests\unit\services\financial_reconciliation_service\test_reconciliation_service.py tests\unit\services\financial_reconciliation_service\test_reconciliation_repository.py tests\unit\services\financial_reconciliation_service\test_reconciliation_requested_consumer.py -q`
   - 31 passed.
2. `python -m ruff check tests\unit\services\financial_reconciliation_service\domain\test_reconciliation_run_lifecycle_policy.py`
   - passed after import-path wrapping.

Final scoped validation is recorded in the commit evidence after the full slice gates run.

## Documentation, Wiki, Context, And Skill Decision

Updated the domain state-transition standard, codebase review ledger, and repo-local engineering
context.

No wiki update is required because no operator command, API route behavior, runtime support
workflow, user-facing capability, or published wiki truth changed.

No central Lotus skill change is required. The repeatable guidance is already captured in the
repo-local domain state-transition standard.

## Remaining Work

GitHub issue #659 is locally fixed for the acceptance criteria pending PR CI/QA and issue closure.
Future lifecycle work should continue this pattern for valuation/aggregation jobs, simulation
sessions, transaction booking/correction/restatement, and pipeline-stage policies when those
related issues are selected.
