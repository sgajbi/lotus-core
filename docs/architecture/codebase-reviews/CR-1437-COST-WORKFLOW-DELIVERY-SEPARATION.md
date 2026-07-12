# CR-1437: Cost Workflow Delivery Separation

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Allow the combined transaction-processing runtime to execute cost policy without constructing or
inheriting Kafka delivery state.

## Change

- Split `CostCalculationWorkflow` from `CostCalculatorConsumer` at the existing method boundary.
- Kept transformation, enrichment, cost/lot processing, persistence staging, reconciliation, and
  compatibility outbox behavior on the plain workflow.
- Kept message parsing, correlation context, retry classification, DLQ mapping, consumer-owned
  idempotency, and legacy transaction scope on the compatibility consumer.
- Renamed the structural processor contract to `CostCalculationWorkflowPort` to distinguish the
  interface from the concrete workflow.

## Compatibility

`CostCalculatorConsumer` inherits the same workflow and retains the same constructor, topics,
groups, retries, DLQ behavior, idempotency identity, transaction boundaries, calculations, and
events. No deployed runtime or API contract changed.

## Evidence

- Complete cost-calculator plus target-service unit pack: 185 passed.
- Direct proof confirms the workflow constructs with no Kafka consumer configuration.
- Focused MyPy/Ruff, strict architecture, full source dead-code, and diff gates passed.

## Same-Pattern Decision

Cashflow calculation/rule staging must also become constructible without a Kafka consumer. The
final normal path will use one delivery consumer; legacy cost/cashflow/position consumers remain
temporary compatibility and rollback assets only.

No README, wiki, central context, or skill change is required before runtime topology changes.
