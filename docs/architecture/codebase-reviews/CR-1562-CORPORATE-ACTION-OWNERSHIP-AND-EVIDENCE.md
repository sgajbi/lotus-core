# CR-1562 Corporate Action Ownership And Evidence

Date: 2026-07-14

## Objective

Advance issue #719 by moving corporate-action validation, basis reconciliation, and reconciliation
evidence policy into the unified transaction-processing capability.

## Findings

- Bundle A validation and reconciliation were single-consumer policies under `portfolio_common`.
- The cost infrastructure workflow built deterministic reconciliation identity, summaries, and
  findings through more than 300 lines of untyped dictionary logic.
- Finding status and reason-code vocabularies were open strings inside infrastructure.

## Change

- Added transaction-service-owned corporate-action validation over immutable
  `BookedTransaction`.
- Added service-owned basis reconciliation with a closed reconciliation status vocabulary.
- Added an application evidence builder with typed immutable run and finding records plus closed
  finding and reason-code vocabularies.
- Routed cost and cashflow production callers through the owned domain policies.
- Deleted the obsolete shared validation/reconciliation facades and moved their tests to the owner.
- Reduced `cost_calculation_workflow.py` from 1,617 to 1,309 lines while leaving persistence,
  metrics, and logging in infrastructure.

## Architecture Decision

This is design modularity inside the existing transaction-processing deployable. No workload,
failure-isolation, security, scaling, or ownership evidence justifies another runtime service.

## Compatibility

API, event, topic, database, reconciliation record, deterministic ID, downstream response, and
runtime topology contracts are unchanged.

## Validation

- Corporate-action validation, basis, evidence, workflow, and structure cohorts passed up to 51
  focused tests during the slice.
- The application evidence extraction passed focused MyPy and 46 combined evidence, basis,
  workflow, and structure tests.
- Same-pattern structure guards prevent the retired shared facades from returning.

## Remaining Work

Issue #719 remains open for complete cost/cashflow/position ownership, legacy calculator runtime
retirement, replay/backdating/concurrency proof, and final database/runtime cleanup. Issues #450,
#480, and #481 retain partial allocation, parent-event graph, and lot-lineage gaps.
