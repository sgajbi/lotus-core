# CR-1696: Backdated Position Economics Coalescing

Date: 2026-08-21
Issue: #486
Status: Fixed locally; protected PR and exact-main proof pending

## Objective

Preserve complete position quantity and cost-basis authority when two committed backdated
transactions for the same portfolio and security are processed concurrently. Exactly one epoch
advance remains authoritative and active-runtime replay fan-out remains zero.

## Finding

Exact-main Main Releasability run `32392872624` produced a schedule in which the later
economic-date BUY acquired the cost-basis lock first. Full cost calculation correctly rebuilt all
three transactions, but cost
persistence wrote only the affected suffix beginning at the winning transaction. The earlier
canonical row therefore still had no derived `net_cost` when position history reread the complete
transaction stream. Position quantity was correct, while cumulative cost basis became
`0/30/130` instead of `50/80/180`. The losing request later coalesced by transaction lineage in
the already advanced epoch, so it did not repair the incomplete history.

This was a production correctness race and a regression of #486's exact closure acceptance, not a
wall-clock or runner flake. A favorable earliest-first schedule concealed it.

## Change

- Full cost-basis rebuilds now persist the affected suffix plus calculated prefix rows that lack
  durable base/local economics or Core calculation lineage before position history is staged in
  the same caller-owned transaction. Non-null source-supplied cost values are not treated as
  calculated authority without that lineage.
- Already-governed prefix rows are not rewritten. The two-row and 200-row AVCO replay fixtures
  retain equal statement count, preventing history-depth amplification.
- Incremental calculations retain the existing affected-suffix write boundary.
- Only affected-suffix transactions perform the per-transaction child-state writes in this slice;
  the full rebuild continues to persist its complete governed lot snapshot separately.
- The outward processed-transaction result remains incoming-event scoped, so historical
  transactions are not republished and cashflow/readiness cardinality does not increase.
- A deterministic PostgreSQL barrier holds the first acquired cost lock, proves the contender is
  waiting in `pg_locks`, and then releases both later-first and earliest-first schedules. The proof
  retains one epoch, one three-row rebuild, one zero-work coalesced result, zero replay events,
  exactly one processed event per incoming command, exact canonical local/base costs and lineage,
  and exact cumulative position history and lineage.

The change does not move either the cost or position lock, add a post-lock maximum-date recheck, or
change Kafka concurrency. Those rejected experiments remain excluded.

## Same-Pattern Decision

The audited `list_all_transactions` backdated rebuild is repaired because any row without durable
base/local economics or Core calculation lineage receives the full calculation's authority in the
same unit of work. The ordinary
`load_replay_window` path remains protected by same-key cost serialization and later event
processing; broader separation of complete internal calculation authority from incoming-only
effect publication remains owned by #719. No duplicate issue is required. #795 remains the
separate ordered-delivery and capacity owner.

The audit also proved that named fee components stored in `transaction_costs` are not rehydrated by
the canonical full-history reader. A later rebuild can therefore reconstruct fee inputs from a raw
aggregate `trade_fee` instead of the governed component breakdown. This pre-existing, distinct
fee-authority defect is durably routed to #719 in
[`issuecomment-5359603950`](https://github.com/sgajbi/lotus-core/issues/719#issuecomment-5359603950);
it is not claimed fixed by CR-1696.

## Compatibility

No API, OpenAPI, event schema, Kafka key/partition, database schema/migration, dependency, image,
or topology changes. Transaction calculation formulas, numeric policy, epoch numbering,
idempotency, replay-event behavior, and caller-owned rollback remain unchanged. Full rebuilds can
write additional calculated prefix transaction economics only when base/local costs or Core
calculation lineage are absent; this is the intentional correctness change. Incremental and
governed-history statement cardinality remain unchanged.

## Validation

- Focused persistence/calculation/execution unit suite: `38 passed`.
- Deterministic PostgreSQL lock-permutation plus AVCO capacity proof: `3 passed in 43.48s`.
- Touched-source Ruff and MyPy: passed.
- Full transaction-processing contract: `148 passed in 869.65s`.
- Protected PR lanes and exact-main Main Releasability: pending.

## Documentation Decision

Repository context and the Position Calculator wiki source are updated because the zero-work
coalescing invariant depends on complete canonical economics persistence. No README, OpenAPI,
migration, RFC, or central Platform skill/context change is required.
