# CR-1631 Cashflow Rule Source-Version Validation

## Objective

Remove one source-version SQL query per booked transaction from the governed cashflow rule-cache
hit path while preserving bounded rule-change visibility, immutable source lineage, explicit
invalidation, missing-rule recovery, and concurrency safety under GitHub issue #795.

## Measured Finding

Cleanup-fenced exact daily `20260718T002619Z` at clean signed source `45fe19d1e` loaded the
25-rule snapshot only `25` times but executed `89,138`
`CashflowRulesRepository.get_rule_set_version` queries while completing `89,163` transaction
operations. Those source-version reads totalled `1,730.304179s` across concurrent observations at a
`0.019411521s` mean. The run made all `100,000` source transactions durable but reached only
`89,012` snapshots before the fixed deadline.

Cumulative observation time is attribution, not predicted wall-clock savings. Exact fan-in is
therefore required before retaining the implementation and before another daily certification run.

## Changes

- Added `CASHFLOW_RULE_CACHE_SOURCE_VERSION_CHECK_INTERVAL_SECONDS` with a fail-closed production
  parser, a default of five seconds, and a minimum of one second.
- Added an immutable `source_version_checked_at_monotonic_seconds` boundary to each runtime-owned
  cache snapshot.
- Fresh hits inside the bounded interval are SQL-free.
- The first lookup after the interval acquires the existing cache lock and performs one source
  version query. Concurrent lookups reuse that validation result.
- An unchanged fingerprint renews only the validation boundary. A changed fingerprint reloads the
  full immutable rule snapshot before calculation.
- The existing 300-second TTL still forces a complete snapshot reload.

## Preserved Contracts

- Every cached rule retains the rule-set fingerprint and latest effective timestamp.
- `CashflowRuleCache.invalidate()` remains the immediate process-local invalidation path.
- Missing transaction types still force one full reload before terminal no-rule classification.
- Invalidation racing a load or source check cannot publish the invalidated snapshot.
- Rule normalization, calculation behavior, DLQ classification, metrics, SQL schema, transaction
  atomicity, and runtime ownership remain unchanged.

## Same-Pattern Scan

The agreed #795 scope was searched for reference caches that query a source version on every cache
hit. No second implementation exists under `portfolio_transaction_processing_service` or
`portfolio_common`; the governed cashflow rule cache was the only match.

## Validation

- `55` focused cache, repository, and configuration tests pass.
- The transaction-processing unit package plus shared configuration proof passes `919` tests.
- Full MyPy passes across `235` source files.
- Complete architecture guard passes.
- Touched Ruff and format checks pass.
- Architecture documentation catalog, wiki validation, and `git diff --check` pass.

Exact clean fan-in and database-operation count comparison remain required before the change is
classified as retained. The daily, recovery, poison, duplicate/concurrency, and restatement gates
remain blocked on that decision.

## Compatibility And Documentation Decision

No HTTP API, OpenAPI schema, Kafka topic/key/payload, database schema, migration, calculation,
idempotency, outbox, or unit-of-work contract changes. The intentional operator-visible change is
bounded existing-rule update visibility: five seconds by default, or the configured interval.
Repository context, RFC-022, the operations runbook, CR-1371, and authored wiki source are updated.
Publish and strictly verify the wiki only after merge to `main`.
