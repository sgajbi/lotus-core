# CR-1490: Cashflow Workflow Ownership Boundary

Date: 2026-07-11
Issue: #468
Status: Active workflow isolated; compatibility delivery deletion pending

## Objective

Make the combined transaction runtime depend on a clearly named cashflow application workflow
rather than a retired Kafka consumer package, while preserving cashflow semantics, rule-cache
behavior, epoch fencing, idempotency, replay, and linked-leg validation.

## Findings

The active cashflow policy and staging workflow shared `consumers/transaction_consumer.py` with
Kafka decoding, session construction, retry, physical replay handling, commit/rollback, and DLQ
routing. Target composition imported that consumer module as `cashflow`, making active application
ownership appear to be delivery ownership and allowing future target code to depend on retired
transport behavior.

## Change

- Moved rule caching, transaction validation, semantic event identity, epoch fencing, cashflow
  calculation, persistence staging, and compatibility outbox staging to
  `app/cashflow_calculation_workflow.py`.
- Updated target composition and the cashflow compatibility adapter to import typed workflow
  symbols directly.
- Reduced `consumers/transaction_consumer.py` to a quarantined compatibility shell for Kafka,
  sessions, physical replay, commit/rollback, retry, and DLQ characterization.
- Migrated workflow test patches to the owning module and added a target import-confinement test.

## Compatibility

Cashflow amounts, signs, classifications, timing, linked-leg rules, semantic idempotency, cache
refresh behavior, epoch rejection, event payloads, database state, and public contracts are
unchanged. This is design modularity inside the existing unified deployable, not a runtime split.

## Validation

- `219` cashflow, combined-runtime, transaction-spec, and portfolio-flow tests passed.
- Touched-source MyPy and Ruff passed.
- Vulture, architecture boundary, in-process modularity, and in-process boundary guards passed.
- The target Docker image rebuilt successfully and imported both `ProcessTransactionUseCase` and
  `CashflowCalculationWorkflow` from the installed runtime.

## Remaining Work

Migrate domain-oriented tests away from `CashflowCalculatorConsumer`, retain only delivery-specific
characterization that still protects historical behavior, then delete the compatibility shell.
Move surviving cashflow application/domain/infrastructure packages under target-owned domain names
only after import, image, test, documentation, and downstream scans prove the move.

No platform skill change is required: current backend delivery and codebase-review skills already
require design modularity before runtime splitting, same-pattern scans, image import proof, durable
context, and deterministic guards. Repository context is updated because this ownership rule is
Core-specific.
