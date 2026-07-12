# CR-1549: QCP Control-Stage Failure Evidence Review

## Objective

Restore exact-main integration correctness after the QCP operations repository attempted to read a
`failure_reason` attribute that does not exist on `PipelineStageState` or its database table.

## Decision

`pipeline_stage_state` remains a lifecycle gate, not a duplicate reconciliation-run record. QCP now
maps its compatibility `controls_failure_reason` field explicitly to `null`. Durable failure detail
continues to come from `FinancialReconciliationRun` through
`controls_latest_reconciliation_failure_reason`.

Adding an unpopulated database column would increase schema and ownership complexity without adding
evidence. Removing the response field would break consumers. The compatibility-null mapping keeps
the contract stable and truthful.

## Prevention

- The repository unit fixture now has the same attribute shape as the real ORM model.
- PostgreSQL integration coverage exercises the real `PipelineStageState` mapping.
- The OpenAPI field description identifies the authoritative failure-detail field.

## Validation

- Focused repository unit and QCP PostgreSQL integration tests.
- Ruff, OpenAPI, API vocabulary, and no-alias gates.

## Compatibility And Documentation

The response shape is unchanged. `controls_failure_reason` remains nullable and is now documented as
a compatibility field; consumers should use `controls_latest_reconciliation_failure_reason`.
Repository architecture evidence changes in this review. README, wiki, and repository context do not
change because service ownership and operator workflow are unchanged.
