# CR-1471: Ordered Append And Backdated Capacity

Date: 2026-07-10
Issue: #468
Status: Hardened locally; deployed load proof pending

## Objective

Keep normal ordered transaction processing proportional to the new work while preserving full,
deterministic recalculation for backdated or ambiguously ordered events.

## Decision And Implementation

The cost engine was linear after FIFO and AVCO data-structure fixes, but the workflow still loaded
and recalculated complete portfolio/security history for every event. Repeating that operation for
ordered daily arrivals made the workflow quadratic over time.

The workflow now persists `cost_basis_processing_state`, a versioned canonical ordering watermark
for each portfolio/security key. It uses the same total ordering function as engine sorting. An
incoming event may use incremental processing only when:

- checkpoint engine version and portfolio cost-basis method match;
- portfolio/security identity matches;
- the incoming transaction sorts strictly after the checkpoint;
- the registry lot behavior is explicitly approved for incremental processing.

Missing, stale, incompatible, same-order, backdated, or unsupported state forces the existing full
deterministic rebuild. Existing portfolios are not backfilled optimistically: their first event
performs a full rebuild and atomically establishes a checkpoint. A failed calculation, suffix
write, lot update, checkpoint update, cashflow, position update, or outbox write rolls back the
combined unit of work.

Every full rebuild persists its complete rebuilt open-lot snapshot before the checkpoint, even when
the incoming event is non-lot-mutating, such as a dividend. The trigger type cannot suppress
rebuilt quantity or local/base cost state that a later incremental FIFO or AVCO disposal restores.

Ordered lot openings and non-lot events calculate only the incoming row. State-dependent disposal
and basis-transfer events restore current positive open-lot state, calculate the incoming row, and
reconcile changed lot state. Backdated events recalculate and persist the affected suffix while
leaving the checkpoint on the latest canonical event.

CR-1473 narrows ordered FIFO `consume_lot` processing further. It streams open source lots in the
same date, original-quantity, and transaction-ID order used by the engine and stops after the
requested disposal quantity is covered. Persistence updates only that selected set and fails if a
selected source row is missing; omitted later lots remain unchanged. CR-1479 adds a distinct AVCO
aggregate checkpoint: ordered acquisitions and disposals restore one pooled source while set-based
database reconciliation keeps every externally visible source row current. Basis transfers,
unsupported corporate actions, and full rebuilds continue to use complete snapshots.

## Capacity Evidence

`make profile-cost-processing-modes` writes
`output/cost-processing-mode-capacity-profile.json`. The profile separates ordered lot opening,
ordered disposal, and backdated rebuild. It measures the pure parser/sorter/cost-engine boundary;
it excludes database, Kafka, outbox, cashflow, and position time and is not a production SLO.

Local 8,000-history results, five ordered samples per method:

| Method | Workload | Average request latency | Errors |
|---|---|---:|---:|
| FIFO | ordered opening append | 0.078ms | 0 |
| FIFO | ordered disposal append, 1 restored lot | 0.065ms | 0 |
| FIFO | backdated rebuild, 8,001 rows | 260.212ms | 0 |
| AVCO | ordered opening append | 0.090ms | 0 |
| AVCO | ordered disposal append, 1 restored source | 0.086ms | 0 |
| AVCO | backdated rebuild, 8,001 rows | 373.613ms | 0 |

The results prove that ordinary lot opening no longer scales with history and that ordered
FIFO disposal no longer scales with unrelated later open lots: the same 8,000-row scenario
previously restored 6,000 lots and averaged 57.770ms. CR-1479 similarly reduces ordered AVCO
application restoration from 6,000 source rows at 112.493ms to one pooled source at 0.086ms. The
durable pool is versioned transactional state, not an unowned cache, and source-lot reconciliation
remains explicit database work because source lineage is externally visible.

## Validation And Compatibility

- focused cost/repository/adapter unit packs passed;
- ordered append and backdated workflow tests passed for bounded FIFO, complete AVCO, and fallback;
- branch-built PostgreSQL BUY/SELL, FIFO/AVCO backdated correction, epoch, suffix, checkpoint, and
  rollback proof passed, including selected-lot persistence;
- migration contract has one Alembic head at `c106b2c3d4eb`;
- scoped Ruff, format, MyPy, and diff checks passed.

No API, event payload, Kafka topic/group, cashflow, position, P&L methodology, or downstream
contract changed. The schema change is additive. Runtime mode and open-lot restore metrics use only
bounded labels (`mode`, `cost_basis_method`) and do not expose business identifiers.

## Remaining Work

This is not final cutover capacity certification. Database query count/plans, connection-pool use,
end-to-end p50/p95/p99, partition ordering and lag, backlog drain, failure recovery, shutdown drain,
and comparison with the three-worker baseline remain required. Historical AVCO lot evidence still
needs an idempotent reconciliation/backfill before source products can claim current post-cutover
supportability.
