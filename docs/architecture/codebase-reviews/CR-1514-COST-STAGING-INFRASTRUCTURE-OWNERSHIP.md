# CR-1514: Cost Staging Infrastructure Ownership

Date: 2026-07-11
Issue: #468
Status: Implemented locally; workflow and repository extraction pending

## Objective

Remove the mixed-layer legacy cost event processor and place compatibility SQL/outbox staging in
the target infrastructure adapter behind the existing transaction-processing application port.

## Finding

`cost_calculation_processor.py` combined a structural workflow contract, concrete SQL repository
construction, physical idempotency, outbox staging, and valid-event sequencing. Treating that file
as an application use case would move infrastructure dependencies into the target application
layer and duplicate the existing `ProcessTransactionUseCase` boundary.

## Implementation

- Folded compatibility event staging and its transitional workflow protocol into
  `CostProcessingCompatibilityAdapter`.
- Kept the combined normal path behind `CostProcessingPort` and the caller-owned SQLAlchemy unit of
  work.
- Kept the old physical idempotency claim only in the quarantined compatibility consumer, alongside
  its concrete repository construction and retry/DLQ lifecycle.
- Deleted `cost_calculation_processor.py`, its dependency bundle, factory, and generic processor
  contract.
- Updated unit and PostgreSQL concurrency tests to invoke the target adapter and added a structural
  guard against restoring the mixed-layer module.
- Corrected tests to prove both raw compatibility dependency errors and application error mapping.

## Boundary And Compatibility Decision

No new application use case was added: `ProcessTransactionUseCase` already coordinates atomic cost,
cashflow, position, semantic idempotency, and commit behavior. The staging adapter is explicitly
transitional infrastructure because it still invokes private methods on the legacy workflow and
passes concrete SQL/outbox collaborators.

No calculation, API, event, topic, payload, service idempotency name, database schema, transaction
scope, retry/DLQ classification, or downstream contract changed.

## Validation

- Target service plus cost workflow/consumer/private-banking AVCO cohort: `194 passed`.
- Final focused adapter, consumer, and retirement proof: `58 passed`.
- Repository-native PostgreSQL transaction-processing contract: `32 passed in 127.88s`.
- Ruff, formatting, targeted MyPy, application-layer, dependency-inversion, domain-layer,
  infrastructure-adapter, repository-transaction, testability, and modularity gates passed.
- Reconciliation onto the post-PR-727 mainline passed `58` focused tests plus targeted MyPy, Ruff,
  and diff checks while preserving current pipeline-readiness ownership.

## Same-Pattern Scan

The target `app/application` and `app/use_cases` packages contain no SQLAlchemy, concrete outbox,
or concrete idempotency imports. A repository-wide processor-name/dependency scan identified
`position_valuation_calculator/app/valuation_processor.py` as the closest remaining sibling pattern:
it combined application sequencing with a concrete session dependency factory. CR-1516 moved
construction to explicit infrastructure composition and kept the still-transitional processor out
of a false application package. Do not bulk-move generic query services merely because their
filenames contain `service`.

## Follow-Up

Extract cohesive calculation and publication capabilities from the legacy workflow behind public
target ports, then move the SQL repository to target infrastructure. Delete the compatibility
consumer only after delivery tests, rollback assumptions, downstream contracts, and canonical
runtime evidence prove it is no longer required.
