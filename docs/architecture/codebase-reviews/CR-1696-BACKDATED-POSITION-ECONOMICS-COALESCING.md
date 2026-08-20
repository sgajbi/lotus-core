# CR-1696: Backdated Position Economics Coalescing

Date: 2026-08-21
Issue: #486
Status: Correctness fix-forward in progress after PR #968; protected PR and exact-main proof pending

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
  current, output-bound Core cost authority before position history is staged in the same
  caller-owned transaction. Authority requires durable base/local economics, the exact v2
  transaction-cost algorithm and numeric policy, and a receipt bound to the complete persisted
  output.
- Raw persistence stages positive named fee components atomically with the transaction. The
  canonical full-history reader eagerly rehydrates the five governed component types in one query,
  rejects unsupported, duplicate, or currency-conflicting evidence, and lets named authority win
  over a disagreeing aggregate `trade_fee`. Prefix repair can therefore replace economics without
  reclassifying stamp duty, exchange fees, GST, or other fees as brokerage. Explicit all-zero named
  authority removes prior positive component rows and remains idempotently zero; all-`None` sparse
  events do not invent a component correction.
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

The audited `list_all_transactions` backdated rebuild is repaired because any row without current,
output-bound Core transaction-cost authority receives the full calculation's authority in the
same unit of work. The ordinary
`load_replay_window` path remains protected by same-key cost serialization and later event
processing; broader separation of complete internal calculation authority from incoming-only
effect publication remains owned by #719. No duplicate issue is required. #795 remains the
separate ordered-delivery and capacity owner.

The bounded canonical history and raw-persistence fee gap is fixed here because selective prefix
repair newly reaches those rows. #719 retains alternate/replay reader hydration, historical
aggregate-versus-component migration and reconciliation, transaction ordering, and broader
large-history capacity work; CR-1696 does not claim those program-level outcomes.

## Compatibility

No API, OpenAPI, event schema, Kafka key/partition, database schema/migration, dependency, image,
or topology changes. Transaction calculation formulas, numeric policy, epoch numbering,
idempotency, replay-event behavior, and caller-owned rollback remain unchanged. Full rebuilds can
write additional calculated prefix transaction economics only when current output-bound Core
authority is absent; this is the intentional correctness change. Named-fee raw ingestion adds one
bounded delete/replace operation only when named components are present; ordinary aggregate-only
transactions keep their existing statement count. Incremental and governed-history calculation
statement cardinality remain unchanged.

## Validation

- Focused persistence/calculation/repository unit suite: `164 passed`.
- Deterministic PostgreSQL named-fee lock permutations plus raw-persistence correction/rollback:
  `3 passed in 74.38s`.
- Touched-source Ruff and MyPy: passed.
- Full transaction-processing contract at the production-code head: `147 passed`; one query-shape
  guard misclassified the new joined history query as a duplicate point read after `942.55s`.
  The corrected guard proves zero point reads and exactly one joined fee-authority history read;
  its focused PostgreSQL rerun passed in `76.24s`. The protected PR lane remains the final complete
  contract rerun authority.
- Protected PR lanes and exact-main Main Releasability: pending.

## Documentation Decision

Repository context and the Position Calculator wiki source are updated because the zero-work
coalescing invariant depends on complete canonical economics persistence. No README, OpenAPI,
migration, RFC, or central Platform skill/context change is required.
