# CR-1438: Cashflow Workflow Delivery Separation

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Allow the combined transaction-processing runtime to execute cashflow policy without constructing
Kafka delivery state or retaining consumer-owned transaction control.

## Change

- Split a plain `CashflowCalculationWorkflow` from `CashflowCalculatorConsumer`.
- Kept rule-cache freshness/version checks, rule resolution, semantic idempotency, epoch fencing,
  cashflow calculation, persistence staging, and compatibility outbox staging on the workflow.
- Kept message parsing, physical delivery claim, stale-replay detection, retry/DLQ classification,
  and compatibility commit/rollback decisions on the consumer.
- Tightened five legacy `Any` return paths so the complete moved source is MyPy-clean.

## Compatibility

The consumer inherits the workflow and retains its current constructor, topics, groups, physical
and semantic fences, stale replay behavior, rule cache, events, retries, DLQ behavior, and commits.
No deployed runtime, database, or API contract changed.

## Evidence

- Complete cashflow-calculator plus target-service unit pack: 104 passed.
- Direct proof confirms the workflow constructs with no Kafka consumer configuration.
- Full touched-source MyPy, scoped Ruff, strict architecture, full source dead-code, and diff gates
  passed.

## Same-Pattern Decision

The final normal path needs one target delivery consumer using plain cost and cashflow workflows,
the position policy adapter, and one SQLAlchemy UoW. Reprocessing remains a separate use case and
consumer within the same deployable because its epoch, ordering, throttle, and backlog semantics
differ from live booked-transaction processing.

No README or wiki change is required before deployment topology changes. Repository context is
updated with the one-normal-consumer rule so agents do not reproduce the compatibility topology.
