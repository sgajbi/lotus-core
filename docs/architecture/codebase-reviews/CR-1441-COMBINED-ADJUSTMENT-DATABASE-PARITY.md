# CR-1441: Combined Adjustment Database Parity

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Prove the concrete combined workflows, repositories, mappers, idempotency, and SQLAlchemy UoW on a
real business path rather than only test staging ports.

## Contract Precondition

`transactions.persisted` is emitted after ingestion owns and commits the canonical transaction
row. Transaction processing enriches that row and derives cost/lot, cashflow, position, and outbox
state; it does not duplicate ingestion persistence ownership.

## Evidence

A PostgreSQL-backed `ADJUSTMENT` path proves:

- one canonical transaction remains;
- one governed cashflow is persisted;
- one position-history record is persisted;
- one `portfolio-transaction-processing` physical idempotency fence is persisted;
- `ProcessedTransactionPersisted` and `CashflowCalculated` compatibility outbox events are staged;
- result counts report one processed transaction, cashflow, and position record;
- redelivery returns `DUPLICATE` and does not add rows.

The integration test passed with the real `CostCalculationWorkflow`,
`CashflowCalculationWorkflow`, position policy, repositories, shared mapper, UoW, and PostgreSQL
constraints.

## Database Structure Decision

No schema change is required for this slice. `transactions`, cost/lot state, `cashflows`, and
position history/state encode different financial invariants, audit questions, retention, and
indexing needs. Runtime consolidation removes process and transaction-stage complexity; it does not
justify collapsing these domain tables. Obsolete stage-control or compatibility structures may be
removed only after usage, migration, rollback, and downstream scans prove they are redundant.

## Compatibility

No deployed runtime or schema changed. Existing foreign keys and table ownership remain active and
provided useful contract enforcement during the proof.

## Follow-Up

Add concrete BUY/SELL and replay parity, then measure steady-state throughput/query counts before
runtime registration and legacy service removal.

No README/wiki change is required because runtime and schema truth are unchanged.
