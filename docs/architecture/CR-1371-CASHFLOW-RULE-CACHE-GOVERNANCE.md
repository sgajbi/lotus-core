# CR-1371 Cashflow Rule Cache Governance

## Objective

Fix GitHub issue #576 by governing the cashflow rule cache with source version metadata,
explicit stale-read behavior, invalidation ownership, metrics, and tests.

## Changes

- Added `CashflowRuleSetVersion` and `CashflowRulesRepository.get_rule_set_version()`.
- Added rule-set version and latest effective timestamp metadata to `CashflowRuleCacheState` and
  each `CachedCashflowRule`.
- Changed fresh cache reads to verify the source rule-set version before serving a cached rule.
- Kept TTL expiry and missing-rule reload behavior.
- Kept explicit process-local invalidation through `invalidate_cashflow_rule_cache()`.
- Added `cashflow_rule_cache_events_total` for hit, miss, reload, stale, invalidation, and
  missing-rule cache events.

## Expected Improvement

- Prevents rule changes from remaining hidden until TTL expiry when `cashflow_rules.updated_at`
  changes.
- Makes cache freshness observable.
- Preserves low-cost cache hits when the source version is unchanged.
- Keeps the cache as governed reference data rather than persistence-critical transaction state.

## Stale-Read And Invalidation Policy

- Default TTL still comes from `CASHFLOW_RULE_CACHE_TTL_SECONDS`.
- A cached rule is served only when the TTL is fresh and the source version fingerprint matches.
- Source version is derived from rule count and max `cashflow_rules.updated_at`.
- Missing rules force one immediate full reload before the message is classified as no-rule.
- Explicit invalidation clears only the current process and records an invalidation metric.
- Multi-process deployments must propagate source-owned invalidation by updating
  `cashflow_rules.updated_at`; workers detect the changed source version before serving cached
  rules.

## Tests Added

- Repository version-query test for count/latest-update fingerprinting.
- Cache tests for TTL hit/expiry, missing-rule reload, explicit invalidation, source-version
  change, and concurrent refresh.
- Metric assertions for hit, miss, reload, stale, and missing-rule outcomes.

## Validation Evidence

```powershell
python -m pytest tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\repositories\test_cashflow_rules_repository.py -q
```

Final lint, docs, architecture, and diff checks are recorded in the issue comment before commit.

## Downstream Compatibility Impact

No API route, DTO schema, OpenAPI schema, database schema, Kafka topic, event payload, cashflow
calculation output, or runtime topology changed. Cache invalidation is stricter when source rule
metadata changes.

## Same-Pattern Scan

The touched cache remains scoped to cashflow rules. No additional in-memory cache was added. Future
reference-data caches must carry source version/effective metadata, explicit stale-read behavior,
and bounded metrics before use.

## Docs, Context, And Skill Decision

- Operations runbook updated with cache settings, stale-read policy, and metrics.
- Repository context updated with the cache governance rule.
- No platform skill update is required for this slice; the repo-local rule is now in code, tests,
  runbook, ledger, and context.

## Remaining Hotspots

The invalidation hook is process-local by design. Cross-process invalidation depends on source rule
updates moving `cashflow_rules.updated_at`; a future administrative rule-write API should make that
ownership explicit if rules become mutable through Core APIs.
