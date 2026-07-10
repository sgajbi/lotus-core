# CR-1466: Batched Cost FX Effective Rates

Date: 2026-07-10
Issue: #468
Status: Hardened locally; full-history capacity proof pending

## Objective

Remove transaction-count database query growth from cross-currency cost recalculation while
preserving the deterministic latest-rate-on-or-before methodology used by FIFO, AVCO, fees, and
backdated correction.

## Implementation

- Grouped the recalculated timeline by normalized trade/base currency pair.
- Added one bounded repository query per pair that returns the latest seed rate before the earliest
  requested date plus all rates through the latest requested date.
- Selected each transaction's effective rate with ordered binary search.
- Mapped SQLAlchemy rows to immutable `EffectiveFxRate` domain records at the repository boundary.
- Removed the now-unused single-date repository method and its transitional ORM-return exception.
- Preserved the no-query path for same-currency transactions and retryable failure when no
  effective rate exists.
- Failed before child cost/lot writes when the canonical transaction row is unexpectedly missing.

For `N` cross-currency transactions over `P` distinct currency pairs, FX reads move from `N` to
`P`. A 300-transaction single-pair unit scenario now performs one repository read. This is not an
in-memory or distributed cache: every processing attempt reads the authoritative effective window,
so no cache invalidation or stale-rate behavior is introduced.

## Validation Evidence

- focused cost repository and workflow tests: 51 passed;
- cost and target transaction-processing unit pack: 236 passed;
- MyPy: 37 source files passed;
- repository output-shape, transaction-boundary, in-process modularity, in-process boundary, and
  strict architecture guards: passed;
- combined PostgreSQL transaction-processing contract: 17 passed;
- Ruff, format, documentation, and diff checks: passed.

The tests prove one read for 300 same-pair rows, one read per distinct pair, seed-plus-window query
shape, currency normalization, exact effective-date transitions, missing-seed failure, reversed
window rejection, persistence-neutral output, backdated cross-currency parity, and rollback.

## Compatibility And Remaining Work

API, Kafka, database schema, event count, cost methodology, selected FX values, idempotency, and
deployment topology are unchanged. The missing-rate path remains retryable. The missing canonical
row now fails explicitly before dependent child writes instead of reaching an attribute error or
attempting partial persistence.

This slice improves design and runtime complexity inside the target deployable; it does not create
another runtime service. Full transaction-history loading and recalculation remain the correctness
baseline. Long-history query plans, CPU/memory limits, event throughput, database-pool utilization,
consumer lag, and shutdown drain still require measured capacity evidence before runtime cutover.
README navigation and public API documentation do not change. The repository context, cost
methodology, authored wiki, consolidation ledger, and review ledger are updated because developer
and operator behavior changed. No platform skill change is required: existing backend-delivery and
codebase-review guidance already caught and prohibited the ORM boundary regression during this
slice.
