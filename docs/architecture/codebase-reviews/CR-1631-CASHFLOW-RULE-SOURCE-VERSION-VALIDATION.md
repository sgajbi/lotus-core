# CR-1631 Cashflow Rule Source-Version Validation

## Objective

Determine whether bounding the cashflow rule-cache source-version query could materially improve
the governed transaction-processing workload while preserving rule freshness, immutable source
lineage, explicit invalidation, missing-rule recovery, and concurrency safety under GitHub issue
#795.

## Measured Finding

Cleanup-fenced exact daily `20260718T002619Z` at clean signed source `45fe19d1e` loaded the
25-rule snapshot only `25` times but executed `89,138`
`CashflowRulesRepository.get_rule_set_version` queries while completing `89,163` transaction
operations. Those source-version reads totalled `1,730.304179s` across concurrent observations at a
`0.019411521s` mean. The run made all `100,000` source transactions durable but reached only
`89,012` snapshots before the fixed deadline.

Cumulative observation time was attribution, not predicted wall-clock savings. The experiment was
therefore required to pass exact clean fan-in before retention or another daily certification run.

## Bounded Experiment

Signed experiment head `31ac198a43d0263940ee3c349caffd88ee521155` added a configurable
five-second source-version validation interval, an immutable validation timestamp, SQL-free cache
hits inside the interval, and concurrency-coalesced revalidation under the existing cache lock. It
preserved the 300-second full-refresh TTL, explicit invalidation, missing-rule reload,
invalidation-generation fencing, and immutable source lineage.

The implementation passed `55` focused cache, repository, and configuration tests, `919`
transaction-processing/shared-configuration tests, MyPy across `235` source files, the complete
architecture guard, Ruff, formatting, documentation, wiki, JSON, and diff guards. Same-pattern
search found no second source-query-on-hit reference cache in the agreed transaction-processing and
shared-common scope.

## Exact Fan-In Evidence

The retained parent baseline `20260717T231632Z` at clean signed source `a8d6ee302` completed exact
1,000-row reconciliation with `100.608s` drain and `999` version queries totalling `13.389479s`.

Two cleanup-fenced exact runs at clean signed experiment head `31ac198a4` both completed exact
1,000-row reconciliation with attempts `2/2`, zero repeats, one portfolio aggregation, zero governed
errors, and final outbox `0/0`:

- `20260718T030244Z`: `110.821s` drain, `19` version queries totalling `0.306107s`; JSON SHA-256
  `FDADB8C577CBF51CB1DF8CE7592DBC0CAB0707B46D1CEE5B8F2FA6D206E02AB3`; Markdown SHA-256
  `822837CC2D676B5A674B6DF8CA6E443DA8F8DA410BB77F670BE6F6CB9E7D0452`.
- `20260718T031229Z`: `110.768s` drain, `19` version queries totalling `0.374872s`; JSON SHA-256
  `4A5428C502D5806BC96DD358C56FC6712F5D89A81DAA446315A6DED8D7D0AC89`; Markdown SHA-256
  `25EE574AB0EB1269EB442321B3F978A63F212C2D9F1569F92D63ED68C9C3EA90`.

The query count fell by `98.10%`, but drain regressed by `10.15%` and `10.10%` in two consecutive
exact runs. The second run also had lower database pressure than the first (`46/7/16` peak
total/active/idle-in-transaction connections and `1/1` lock waiters/blocked sessions), so the
repeated end-to-end result does not support retaining the added cache policy.

## Decision

Rejected and reverted forward. Immediate source-version validation before a fresh cache hit remains
the canonical contract. Do not reintroduce a validation interval without new workload evidence that
proves end-to-end improvement; query-count reduction alone is insufficient.

Daily, recovery, poison, duplicate/concurrency, and restatement gates remain withheld until a new
bounded change first proves exact fan-in improvement. GitHub issue #795 remains the durable owner of
the unresolved capacity work.

## Compatibility And Documentation Decision

The experiment and its operator configuration were removed. No HTTP API, OpenAPI schema, Kafka
topic/key/payload, database schema, migration, calculation, idempotency, outbox, or unit-of-work
contract changed. Repository context, this review record, CR-1630, the review ledger, and the
campaign contract retain the no-repeat evidence. RFC-022, the operations runbook, CR-1371, and wiki
source return to their pre-experiment truth, so this rejection requires no additional wiki change.
