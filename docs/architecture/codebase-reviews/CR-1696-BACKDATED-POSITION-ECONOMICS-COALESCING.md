# CR-1696: Backdated Position Economics Coalescing

Date: 2026-08-21
Issue: #486
Status: PR #971 validation in progress; exact-main proof pending

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
  current, input-and-output-bound Core cost authority before position history is staged in the same
  caller-owned transaction. Authority requires durable base/local economics, the exact v2
  transaction-cost algorithm and numeric policy, and a receipt bound to the current normalized
  inputs and complete persisted output.
- Raw persistence stages positive named fee components atomically with the transaction. The
  canonical full-history reader eagerly rehydrates the five governed component types in one query,
  rejects unsupported, duplicate, or currency-conflicting evidence, and lets named authority win
  over a disagreeing aggregate `trade_fee`. Prefix repair can therefore replace economics without
  reclassifying stamp duty, exchange fees, GST, or other fees as brokerage. Explicit all-zero named
  authority removes prior positive component rows and remains idempotently zero; all-`None` sparse
  events do not invent a component correction.
- Transaction-cost input lineage binds the normalized named fee components, not the mapper's
  redundant aggregate `trade_fee` string. PostgreSQL scale expansion such as `2.00` to
  `2.0000000000` therefore preserves replay identity, while a component or amount change still
  changes the input hash.
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
input-and-output-bound Core transaction-cost authority receives the full calculation's authority in the
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
write additional calculated prefix transaction economics only when current input-and-output-bound Core
authority is absent; this is the intentional correctness change. Named-fee raw ingestion adds one
bounded delete/replace operation only when named components are present; ordinary aggregate-only
transactions keep their existing statement count. Incremental and governed-history calculation
statement cardinality remain unchanged.

## Validation

- Focused persistence/calculation/repository unit suite: `164 passed`.
- Deterministic PostgreSQL named-fee lock permutations plus raw-persistence correction/rollback:
  `3 passed in 74.38s`.
- Touched-source Ruff and MyPy: passed.
- Late-review input-authority fix: `118 passed` across the warning-strict calculator and
  application calculation suites; full-repository MyPy passed across `318` source files. The
  regression proves quantity and gross-amount corrections invalidate an otherwise intact prior
  output receipt.
- PR #970 merged as `05476fae8a86e750434298ad2f7e41a2c761c165` before PR Merge Gate run
  `32419579664` became terminal. Its transaction-processing shard then failed with `3 failed,
  145 passed`; downstream coverage/runtime lanes were skipped. This merge is not certification.
  The failure exposed scale-sensitive hashing of the redundant named-fee aggregate.
- Signed fix-forward commit `da2620de3987c3fad2747f4ed65f248d4c52a535`: `114 passed` across
  warning-strict calculator and engine-input tests; both deterministic PostgreSQL lock
  permutations passed in `67.71s` with current input-and-output authority for every canonical row.
- The first full fix-forward transaction-processing run reached `147 passed` and one failure in
  `923.17s`. Its AVCO capacity fixture omitted material product type and asset class, so it
  truthfully exercised stale-authority repair rather than the intended governed-history fast path.
  Signed fixture correction `6d6116a78048a96dfeff3002403688d7da72038d` passed the focused
  PostgreSQL 2-versus-200 history proof in `74.93s` with equal statement counts.
- Complete local transaction-processing contract at signed code/test head `6d6116a78048a96dfeff3002403688d7da72038d`:
  `148 passed in 979.34s`.
- Independent read-only review at that exact SHA found no code, test, documentation,
  compatibility, or scope-boundary blocker.
- PR #971 run `32425106451` passed every functional shard, including the complete transaction
  processing contract, but its combined gate rejected changed-file branch coverage at `84.18%`
  against the governed `85%` floor. Fix-forward tests now prove malformed persisted price,
  disposition-source failure, and negative disposed-basis paths fail closed without lot or
  calculated-cost side effects; the focused warning-strict calculator suite passes `110` tests
  and covers `134/158` branches (`84.81%`) before the additional combined-suite coverage is added.
- PR #971 protected lanes and exact-main Main Releasability remain pending.

## Documentation Decision

Repository context and the Position Calculator wiki source are updated because the zero-work
coalescing invariant depends on complete canonical economics persistence. No README, OpenAPI,
migration, RFC, or central Platform skill/context change is required.
