# CR-1473: Bounded FIFO Lot Restoration

Date: 2026-07-10
Issue: #468
Status: Hardened locally; deployed query-plan proof pending

## Objective

Keep a strictly ordered FIFO disposal proportional to the source lots it actually consumes without
weakening deterministic ordering, insufficient-holdings rejection, or persisted basis integrity.

## Decision

The application selects bounded restoration only for an ordered FIFO transaction whose registry
lot behavior is `consume_lot`. The repository streams positive lots in canonical source order:

1. transaction date ascending;
2. original transaction quantity descending;
3. source transaction ID ascending.

It stops when cumulative open quantity covers the disposal. If holdings are insufficient, all open
lots reach the domain engine and the existing domain error remains authoritative.

The calculation result carries an explicit lot-state update scope. Bounded FIFO uses
`selected_lots`; AVCO, basis transfers, and full rebuilds use `complete_snapshot`. Selected updates
query only the returned source IDs, fail when one is missing, and never close an omitted later lot.
The database index `ix_txn_norm_port_sec_date_qty_id` matches normalized ownership filters and the
canonical order so the server cursor does not require an unrelated full result materialization.

## Measured Improvement

The governed profile remains a pure parser/sorter/engine measurement, not a production SLO.

| 8,000-transaction workload | Before | After |
|---|---:|---:|
| FIFO restored open lots | 6,000 | 1 |
| FIFO ordered disposal average | 57.770ms | 0.065ms |
| AVCO restored source lots | 6,000 | 6,000 |
| AVCO ordered disposal average | 119.745ms | 112.493ms |

AVCO is intentionally unchanged. Its pooled source allocation needs a separate durable aggregate
and source-evidence design; applying FIFO subset persistence would corrupt pooled reconciliation.

## Validation And Compatibility

- 49 workflow/consumer tests passed for bounded FIFO, complete AVCO, and full-rebuild fallback;
- 32 schema/repository tests passed with exact query and index shape;
- PostgreSQL proof returned and updated only the two lots needed for a six-unit disposal and left a
  third later lot unchanged;
- capacity profile v2 reports restored-lot counts and passed five contract tests;
- Ruff, scoped MyPy, Alembic head, and migration SQL contract checks passed.

No API, event, Kafka, cashflow, position, P&L methodology, or downstream response contract changed.
The schema change is an additive index. Remaining evidence is deployed-like query plans, DB/Kafka
p50/p95/p99, pool use, lag, recovery, and shutdown drain.
