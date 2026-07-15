# CR-1624 - Transaction Readiness Pipeline Retirement

## Objective

Remove the obsolete Kafka hop that routed an already-completed atomic transaction through
`pipeline_orchestrator_service` before valuation readiness, while preserving transaction ordering,
epoch fencing, idempotency, outbox atomicity, and downstream event contracts.

## Findings

`ProcessTransactionUseCase` already owns cost, position, cashflow, idempotency, and outbox effects
in one database transaction. The pipeline orchestrator still consumed the compatibility
`transactions.cost.processed` event, rebuilt transaction-stage state, and emitted readiness in a
second transaction. That duplicated ownership, added one consumer group and asynchronous hop, and
made downstream valuation readiness depend on broker delivery after the authoritative financial
effects had committed.

The same review found stale ownership in the event supportability catalog, architecture matrix,
RFC index, operator guidance, and repository context. Those artifacts could have caused future
work to restore the retired path.

## Change

1. Transaction processing stages `TransactionProcessingCompleted` and
   `PortfolioDayReadyForValuation` only after cost, position, and cashflow effects succeed.
2. Normal, repair, and rebuilt/backdated transaction sets use the same deterministic readiness
   registration path and propagate correlation plus `traceparent` lineage.
3. The pipeline processed-transaction consumer and
   `pipeline_orchestrator_processed_txn_group` are removed.
4. The unreachable transaction handler, unit-of-work method, service coordination, state-machine
   policy, event factory, repository methods, integration tests, and transitional guard exception
   are removed.
5. The pipeline runtime retains only portfolio aggregation-to-reconciliation and
   reconciliation-to-controls coordination. Historical transaction-stage rows remain a governed
   retention decision because the same table still stores surviving portfolio-control rows.

## Measured Improvement

- one fewer Kafka consumer and consumer group;
- one fewer asynchronous transaction-readiness hop;
- no duplicate pipeline transaction-readiness implementation;
- more than 1,000 net source/test lines removed in this slice;
- readiness and financial effects now share one rollback boundary;
- event ownership is enforced by catalog and guard tests.

## Compatibility

Kafka topics, event types, payload fields, aggregate IDs, partition identity, API/OpenAPI contracts,
and database schema are unchanged. `transactions.cost.processed`, `cashflows.calculated`, and
`transaction_processing.ready` remain compatibility facts. The first two and
`transaction_processing.ready` have no active in-repo consumer; valuation orchestration continues
to consume `portfolio_security_day.valuation.ready` with its existing contract.

## Validation

- transaction application/readiness unit tests: 149 passed before consumer retirement;
- pipeline orchestrator unit suite: 33 passed after consumer retirement;
- surviving pipeline repository PostgreSQL integration suite: 3 passed;
- event supportability/runtime contract tests: 30 focused tests passed;
- mapping and repository output-shape guard tests: 30 focused tests passed;
- strict MyPy passed for every changed source layer;
- focused Ruff, mapping anti-corruption, repository output-shape, event runtime contract, and diff
  checks passed.

## Follow-Up

Issue #712 remains open. Reassign or retire the two remaining portfolio-day transitions before
deleting the pipeline deployable. Define retention/archive behavior for historical transaction
stage rows before changing the shared `pipeline_stage_state` schema. Do not restore the retired
processed-transaction consumer, group, or pipeline transaction-stage code.
