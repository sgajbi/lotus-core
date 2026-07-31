# CR-1675: Derived-State Portfolio Mutation Fence

## Scope

This review covers GitHub issues #873 and #795 after canonical front-office validation left two
portfolio aggregation jobs pending. Retained PostgreSQL and consumer-DLQ evidence identified the
failed position-timeseries events and the exact database failure.

## Finding

Position-timeseries events are ordered by portfolio and security so independent securities can be
materialized concurrently. Their final application step also mutates portfolio-owned aggregation
jobs. Two security streams for the same portfolio could therefore update overlapping aggregation
rows in opposite orders and deadlock. The consumer then treated the SQLAlchemy database exception
as a terminal validation failure, published the valid event to the DLQ, and committed its source
offset. The authoritative valuation snapshots remained durable, but their position-timeseries
outputs were absent and readiness correctly remained fail-closed.

## Correction

`MaterializePositionTimeseries` now acquires a transaction-scoped PostgreSQL advisory fence keyed
by normalized portfolio identity immediately before portfolio-owned aggregation mutation. The
stable signed 64-bit key uses a versioned namespace and SHA-256 derivation. Per-security reads,
calculation, and position-timeseries writes remain outside the fence, so only the shared mutation
tail is serialized.

`PositionTimeseriesConsumer` now converts SQLAlchemy `DBAPIError` failures into the shared
`RetryableConsumerError`. The common consumer boundary therefore leaves the source offset
uncommitted and relies on ordered Kafka redelivery instead of producing terminal DLQ evidence for
a transient database failure. Existing validation and genuinely terminal error behavior is
unchanged.

## Same-Pattern Review

The review covered database-exception handling across Core consumers and all application callers
of the portfolio aggregation staging, restaging, and invalidation operations. Other inspected
database-backed consumers already retry `DBAPIError`; the position-timeseries consumer was the
outlier. The portfolio-owned mutations are confined to the materializer paths now protected by
the repository port. No duplicate lock helper or second unfenced caller remains in the agreed
derived-state scope.

## Compatibility And Performance

There is no API, OpenAPI, event schema, Kafka topic/group/key/partition, timeout, database schema,
migration, or calculation change. The existing transaction boundary owns lock release. A real
PostgreSQL two-session proof verifies same-portfolio serialization. Distinct portfolios retain
independent keys, and the expensive security-level work stays parallel.

Repository context, the recovery runbook, and this review ledger change because the retry and
shared-mutation invariant is durable operational truth. README, authored wiki, central platform
context, and Lotus skills are explicit no-change: their existing rules already require bounded
database proof, transient-failure recovery, same-pattern review, and exact-main closure.

## Validation

- complete derived-state unit package: `136 passed` with warnings treated as errors;
- focused real-PostgreSQL two-session lock proof: passed;
- targeted Ruff lint and format: passed;
- configured MyPy across `240` source files: passed;
- broader repository-native, protected PR, canonical runtime, and exact-main proof: pending before
  verified issue closure.
