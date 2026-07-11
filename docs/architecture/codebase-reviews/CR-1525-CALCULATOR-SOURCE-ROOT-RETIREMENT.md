# CR-1525: Calculator Source Root Retirement

Date: 2026-07-11
Issue: #468
Status: Implemented locally; aggregate runtime validation pending

## Objective

Delete the final legacy cost calculator source and test roots while retaining domain, workflow,
repository, property, capacity, transaction-RFC, and combined-runtime evidence under the unified
transaction-processing owner.

## Finding

After active cost ownership moved to the target package, the only remaining source was a
non-deployed standalone Kafka consumer. Its 2,065-line test mixed obsolete physical-idempotency,
retry, and DLQ delivery behavior with valuable cost workflow tests. Two capacity profilers also
imported an already-deleted legacy transaction processor, a defect previously masked by generated
build artifacts.

## Implementation

- Extracted 28 retained workflow, persistence, FX, AVCO, linked-cash-leg, corporate-action, and
  reconciliation tests into target ownership.
- Moved cost calculator, strategy, parser, sorter, disposition, property-invariant, checkpoint,
  repository, incremental workflow, and PostgreSQL lot-offset tests into the target test tree.
- Deleted the standalone cost consumer and its standalone persistence test.
- Deleted the legacy cost source and test roots and removed their pytest source paths.
- Updated transaction test manifests to target-owned tests and removed a stale nonexistent
  transaction-processor test path.
- Rewired both capacity profilers to the target-owned `CostBasisTimelineProcessor`.
- Retained unified consumer correlation/error tests and combined PostgreSQL transaction tests as
  the authoritative delivery and atomicity evidence.

## Test Disposition

The deleted standalone consumer tests asserted a runtime that no longer exists: a second physical
idempotency claim, separate database transaction, standalone retry/DLQ routing, and direct
cost-processed publication. Keeping those tests would falsely preserve dual runtime ownership.

Equivalent current behavior is covered at the correct boundaries:

- unified Kafka mapping, correlation, retry classification, and rejection handling in
  `test_transaction_processing_consumer.py`;
- semantic duplicate/conflict and atomic module sequencing in
  `test_process_transaction_use_case.py`;
- cost adapter error mapping in `test_cost_processing_adapter.py`;
- fee, FX, AVCO/FIFO, backdated, corporate-action, duplicate, and rollback behavior in the combined
  PostgreSQL transaction-processing suite;
- direct workflow and domain invariants in the target cost test package.

## Compatibility

No runtime code, API, event, topic, database schema, calculation, persistence, or downstream
contract changed in this slice. The removed consumer was absent from Compose, CI service sets,
release images, and target runtime composition.

## Validation

- Target cost, property, capacity-profile, and image inventory cohort: `279 passed`.
- Retained target workflow plus unified consumer/use-case cohort: `173 passed`.
- Main reconciliation reran the `279`-case target cohort after migrating the newer full-rebuild
  lot-snapshot regression; MyPy, Ruff, repository-output, modularity, and retirement checks passed.
- Ruff passed for moved tests, profilers, and manifests.
- Retired source/test paths are absent and image inventory guards remain blocking.

## Same-Pattern Scan

The position, cashflow, and cost calculator source roots are now absent. Current-state docs, wiki,
database schema ownership paths, test manifests, pytest paths, and capacity scripts were scanned for
stale ownership. Historical CR evidence retains historical paths by design.

## Follow-Up

Run the complete target unit cohort, PostgreSQL transaction-processing contract, capacity profiles,
image import, strict architecture, and deployment/cutover guards. Keep #468 open until that evidence
is recorded.
