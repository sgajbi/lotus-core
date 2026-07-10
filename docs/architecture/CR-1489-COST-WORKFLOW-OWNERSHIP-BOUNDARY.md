# CR-1489: Cost Workflow Ownership Boundary

Date: 2026-07-10
Issue: #468
Status: Active workflow isolated; compatibility delivery deletion pending

## Objective

Make the combined transaction runtime depend on a clearly named cost application workflow rather
than a retired Kafka consumer module, without changing financial behavior or weakening scenario
coverage.

## Findings

`CostCalculationWorkflow` and the retired `CostCalculatorConsumer` shared `consumer.py`. The
workflow also called its own corporate-action reconciliation policies through the delivery subclass
name. Consequently, target infrastructure appeared to depend on legacy Kafka delivery even though
it constructed only the plain workflow.

## Change

- Moved the active workflow, cost policies, value structures, metrics, and staging helpers to
  `cost_calculation_workflow.py`.
- Updated target cost, composition, and AVCO reconciliation adapters to import the workflow directly.
- Removed every workflow-to-delivery-subclass call and added a target import-confinement test.
- Reduced `consumer.py` to a compatibility Kafka/session/retry shell plus temporary re-exports for
  characterization tests that still require migration.

## Compatibility

Cost calculations, FIFO/AVCO behavior, corporate-action reconciliation, event payloads, database
state, metrics, retry behavior, and public contracts are unchanged. No documentation or downstream
consumer migration is required for runtime behavior.

## Validation

`140` focused cost and combined-runtime tests passed. Touched-source MyPy and Ruff passed, as did
Vulture, architecture boundary, in-process modularity, and in-process boundary guards.

## Remaining Work

Migrate domain scenario tests to instantiate `CostCalculationWorkflow` directly, retain only focused
historical delivery characterization where evidence still matters, then delete the compatibility
consumer. Move surviving cost application/domain/infrastructure packages under target-owned domain
names only after import, test, documentation, and downstream scans prove the move.
