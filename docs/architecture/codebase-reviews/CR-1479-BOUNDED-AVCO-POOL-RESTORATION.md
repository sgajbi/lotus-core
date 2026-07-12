# CR-1479: Bounded AVCO Pool Restoration

Date: 2026-07-10
Issue: #468
Status: Hardened locally; historical execution and deployed load proof pending

## Objective

Keep strictly ordered average-cost processing proportional to the incoming transaction without
loading every historical acquisition into the application, while preserving exact pooled quantity,
local/base basis, source lineage, rollback, and downstream tax-lot behavior.

## Decision

Core now owns one versioned `average_cost_pool_state` row per portfolio/security. The row stores the
current pooled quantity, local basis, base basis, instrument identity, and a representative source
transaction. It is not a cache: it is transactional cost-basis state with database constraints,
lineage, compatibility versioning, and caller-owned unit-of-work semantics.

For a strictly ordered AVCO `open_lot` or `consume_lot` event, the application locks and restores
that one aggregate source. Missing, incompatible, stale, source-less, basis-transfer, or corporate-
action state falls back to the deterministic full-history calculation and establishes a complete
checkpoint. Existing portfolios therefore remain correct without optimistic state inference.

`position_lot_state` remains the externally visible source-lineage product. A disposal scales its
existing source rows in set-based PostgreSQL, excludes explicit new acquisition sources, and assigns
the exact Decimal residual to the representative source. The aggregate pool checkpoint and all
source rows update in the same transaction as cost, cashflow, position, idempotency, and outbox
effects. Missing representative state or an invalid residual fails closed and rolls everything back.

## Measured Improvement

The governed profile measures the pure parser/sorter/cost-engine boundary, not deployed throughput.

| 8,000-transaction AVCO workload | Before | After |
|---|---:|---:|
| Restored application sources | 6,000 | 1 |
| Ordered disposal average | 112.493ms | 0.086ms |
| Backdated rebuild rows | 8,001 | 8,001 |
| Backdated rebuild average | 279.240ms | 373.613ms |

The ordinary ordered path no longer grows with acquisition count at application restore time.
Backdated work intentionally remains a complete deterministic rebuild. Database source
reconciliation still updates externally visible source rows and must be measured separately under
deployed-like volume.

## Validation And Compatibility

- 53 focused workflow/consumer tests passed for one-source AVCO restore, ordered acquisition,
  fallback, complete-snapshot corporate-action handling, and checkpoint persistence;
- 20 repository tests passed, including PostgreSQL `FOR UPDATE OF average_cost_pool_state` lock
  shape and set-based exact-residual SQL;
- two combined PostgreSQL scenarios passed in 61.95 seconds, proving pooled/source reconciliation,
  realized P&L, cashflow, cumulative position, duplicate handling, and complete rollback after a
  post-source-update checkpoint failure;
- capacity profile v3 passed six contract tests and reported one restored source with zero errors;
- Alembic has one head at `c106b2c3d4eb`; the schema addition is additive.

No API, event payload, Kafka topic/group, cashflow classification, position methodology, realized
P&L methodology, or downstream source-lot response contract changed.

## Remaining Work

CR-1480 supplies an idempotent bounded audit/apply command that reconstructs pool checkpoints and
verifies every source count plus quantity/local/base sum. It still must run against the reviewed
production-like estate before source products are declared current after cutover.
CR-1481 proves local query-count independence, normalized index selection, and key-scoped lock
behavior. Deployed database p50/p95/p99, connection-pool use/wait, Kafka lag, recovery, and shutdown
drain remain part of #468 capacity certification.
