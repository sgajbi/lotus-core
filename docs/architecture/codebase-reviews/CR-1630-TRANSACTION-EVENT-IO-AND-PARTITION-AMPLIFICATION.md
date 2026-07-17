# Transaction Event I/O And Partition Amplification

## Objective

Remove measured transaction-event I/O and partitioning bottlenecks without weakening transaction
ordering, idempotency, atomic outbox delivery, corporate-action correctness, or downstream event
contracts.

## Finding

The exact 100,000-transaction daily profile
`output/task-runs/20260716T153249Z-bank-day-load.json` reached the fixed two-hour deadline with
`99,314` durable transactions and `96,438` completed valuation jobs/snapshots. Valuation
amplification was already removed: completed jobs had attempt count `2/2`, repeated-processing
count was `0`, and failed outbox/DLQ counts were `0`.

The remaining path still performed unnecessary I/O:

1. every outbox event was explicitly flushed before the surrounding transaction commit even though
   no caller needed the generated database id before commit;
2. routine per-record success details were emitted at `INFO` across transaction persistence,
   transaction economics, cashflow, valuation, outbox, and position-timeseries materialization;
3. `transactions.raw.received` and `transactions.persisted` used `portfolio_id`, serializing every
   independent security in one portfolio through one Kafka partition.

The first certifying fan-in run
`output/task-runs/20260716T175742Z-bank-day-load.json` proved the partition impact. One portfolio
with 1,000 independent securities reconciled correctly but required `1,452.71s`, including
`1,247.665s` of drain time. Because new position rows arrived slowly, portfolio aggregation was
rearmed and completed `525` times for one final portfolio-day row.

## Implemented Direction

1. Outbox staging adds the event to the caller-owned SQLAlchemy transaction and relies on the normal
   commit flush. Dispatcher visibility remains atomic because uncommitted rows are not visible.
2. Routine per-record success logs use `DEBUG`; bounded metrics and all warning, retry, failure,
   stale-state, reconciliation, and lifecycle logs retain their operational levels.
3. The structured-log guard scans the governed hot paths and rejects known high-volume routine
   messages at `INFO`.
4. Transaction ingestion, raw persistence outbox, and repair replay all use the same normalized
   `portfolio_id|security_id` key.
5. Dates and epochs remain outside the key, preserving one position stream across normal,
   duplicate, backdated, reversal, correction, restatement, and corporate-action processing.
6. Cross-security corporate-action and linked-leg correctness remains explicit through dependency
   references, deterministic domain ordering/rebuild, reconciliation, and portfolio-security
   database locks rather than portfolio-wide Kafka serialization.
7. Normal cashflow persistence uses one PostgreSQL conflict-aware insert instead of a savepoint,
   flush, and refresh sequence; duplicate delivery still returns the authoritative stored row.
8. Position-history writes and outbox rows rely on the caller-owned unit-of-work commit instead of
   eager flushes that no caller observes.
9. Residual per-record success logs in reference persistence, Kafka delivery callbacks, outbox
   batches, position locking/deletion, and non-cash FX handling use `DEBUG`. The guard scans every
   persistence repository and rejects the governed messages at `INFO`.

## Measured Result

The rebuilt fan-in run
`output/task-runs/20260716T183314Z-bank-day-load.json` completed with:

- exact `1,000` transactions, completed jobs, snapshots, snapshot events, and position-timeseries
  rows;
- one final portfolio-timeseries row and exactly one aggregation-completed event;
- valuation attempt count `2/2`, repeated-processing count `0`;
- final pending/failed outbox `0/0`;
- `311.457s` total duration and `110.302s` drain time;
- no failed evidence checks.

Compared with the portfolio-key baseline:

- total duration reduced `78.56%`;
- drain time reduced `91.16%`;
- repeated aggregation completions reduced from `525` to `1`.

No aggregation debounce was added. The repeated aggregation was downstream evidence of serialized
upstream arrival and disappeared after the domain-correct partition fix. Adding a timer after that
result would increase freshness latency without a remaining measured defect.

Subsequent bounded evidence kept measurement claims conservative:

- cashflow persistence fan-in `20260716T205744Z` completed exactly with `105.245s` drain;
- deferred position-history flush fan-in `20260716T231755Z` completed exactly with `105.234s`
  drain, effectively unchanged, so the benefit is unit-of-work simplification rather than a claimed
  throughput gain;
- two attempts to skip first-position delete/anchor reads were rejected and fully reverted. Moving
  the lock earlier increased drain to `115.253s`; a concurrency-safe post-lock `MAX` recheck
  increased it to `110.252s`. The latter aggregate query cost more than the empty delete plus
  indexed anchor read it replaced;
- residual hot-path log suppression fan-in `20260717T000106Z` completed with exact `1,000`
  transaction/job/snapshot/position rows, one portfolio row, attempts `2/2`, zero repeats, zero
  blocked sessions, and closed outbox queues. Its `110.256s` drain was unchanged from the
  immediately preceding run, so only the proven log-volume and operational-signal improvement is
  claimed.

The post-cashflow exact daily run `20260716T210418Z` reached `96,511` completed jobs/snapshots at
the fixed deadline, up from `95,871` before that persistence change, but still did not satisfy the
100,000 exact-source acceptance criterion. Another exact daily run is not justified until bounded
evidence identifies a material remaining transaction-economics improvement.

## Compatibility

HTTP APIs, OpenAPI schemas, Kafka topics, event payload schemas, transaction calculations,
idempotency identities, outbox atomicity, and database schemas are unchanged.

The intentional transport behavior change is the transaction partition key:
`portfolio_id` becomes `portfolio_id|security_id` for raw ingestion, persisted transaction facts,
and repair replay. Existing deployed topics require the governed pause/drain/cutover procedure
because historical and new keys can map to different partitions after producer rollout.

## Validation

- `10` outbox repository unit tests and `13` PostgreSQL outbox-dispatcher integration tests passed.
- `105` focused hot-path logging tests passed across persistence, transaction economics, valuation,
  derived state, and the durable guard.
- `51` transaction partitioning/replay/ingestion/persistence tests passed, including real ingestion
  API paths.
- Event runtime contract, event contract test pack, structured-log, domain, application workflow,
  infrastructure adapter, event publisher, repository port, wiki, and documentation guards passed.
- Full `make typecheck` passed for `235` source files.
- Rebuilt diagnostic smoke `20260716T175518Z` completed with exact `10/10` transaction-to-timeseries
  evidence, attempt count `2/2`, zero repeats, and closed queues.
- Rebuilt certifying fan-in `20260716T183314Z` passed with the measured result above.
- Cashflow and position-history PostgreSQL lifecycle, duplicate, repair, backdated, and concurrency
  tests passed before their commits.
- Residual logging validation passed `76` focused tests, the structured-log and complete
  architecture guards, full MyPy across `235` files, Ruff/format, and exact fan-in
  `20260717T000106Z`.

Implementation commits include `23fc6faf3`, `d51adb739`, `ad1ad179d`, `57f8c60e2`,
`4f05be9a5`, and `c230d660a`. Human contract/context alignment is in `9d6dbbbf9`.

## Documentation Decision

Repository context, event contracts, ingestion guidance, the endpoint certification audit, and the
partition migration runbook changed because transport ordering truth changed. No authored wiki or
public OpenAPI change is required. The cashflow, position unit-of-work, and residual logging slices
change no operator workflow or public contract, so they require no additional wiki update.
