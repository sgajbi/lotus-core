# Current Source Revaluation Amplification

## Objective

Remove redundant valuation replay created by current-business-date price and FX observations while
preserving effective-dated correction behavior.

## Finding

The exact-source 100,000-transaction daily profile accepted the complete input workload but failed
to drain within the fixed two-hour budget. At timeout, Core had created `135,982`
`valuation.snapshot.persisted` outbox events for `94,933` unique daily snapshots. PostgreSQL
reached `98.33%` runtime CPU, seven blocked sessions, and a position-timeseries p95 handoff latency
of `1,583.10s`.

The initial price and FX facts were current for the governed business date and arrived before any
positions existed. Both source handlers nevertheless staged durable replay. As positions became
visible, that replay reset already-correct position epochs and repeated valuation and derived-state
work. This was unnecessary because transaction processing already emits one valuation-readiness
fact for every later position mutation, and valuation reads the committed current price and FX
facts.

The next exact-source run proved a second amplification path after source replay was removed.
Scheduler backfill used a different correlation id from transaction readiness, and the valuation
job upsert treated that lineage difference as permission to reopen an already `COMPLETE` job. At
diagnostic interruption, Core had accepted `16,671` transactions but emitted `14,025` valuation
snapshot events for only `9,804` snapshots; `4,204` valuation jobs had been processed twice.
Correlation identity describes operational lineage and cannot authorize replay or state mutation.

## Implemented Direction

1. `source_revaluation.py` owns one framework-neutral temporal scheduling policy for price and FX
   observations.
2. A current-date observation scans currently visible positions for immediate valuation but does
   not stage durable replay.
3. A current-date observation with no visible positions relies on the later transaction-owned
   valuation-readiness fact.
4. Backdated observations retain immediate visible-position jobs plus durable replay.
5. Future observations and observations received before a business-date horizon retain durable
   replay and defer the visible-position scan.
6. FX plans expose whether replay was actually staged rather than defaulting the evidence to true.
7. Immediate price and FX selection compares the persisted source row's `updated_at` with the
   same-day snapshot. Missing or older snapshots are queued; snapshots materialized after the
   source fact suppress delayed duplicate notifications; a later source correction becomes
   eligible again.
8. Completed valuation jobs remain idempotent across different scheduler, readiness, and recovery
   correlation ids. Only price and FX correction handlers can request explicit completed-job
   rearming, after source-versus-snapshot freshness proves that newer authoritative input exists.

## Compatibility

Public APIs, persisted source-event schemas, Kafka topics, and position valuation formulas are
unchanged. The intentional internal behavior change removes redundant current-date replay only.
Backdated and future correction contracts remain unchanged.

## Validation

- `104` valuation-orchestrator and valuation-job repository unit tests passed.
- `3` focused PostgreSQL price/FX freshness lifecycle tests passed.
- Focused Ruff lint and format checks passed.
- Full repository `make typecheck` passed for `235` source files.
- Architecture boundary, domain layer, application workflow policy, and infrastructure adapter
  guards passed.
- Rebuilt diagnostic smoke `20260716T130810Z` passed with `10` transactions, snapshots, completed
  valuation jobs, and snapshot events; valuation attempt count min/max were both `2`, repeated-job
  count was `0`, queues and outbox closed, blocked sessions were `0`, and peak derived-state CPU
  was `4.66%`.

The implementation commits are `4b8a4c772`, `fd7c71fa5`, `e5083a4ff`, and `4709b0b53`. The failed
certifying artifact is `output/task-runs/20260716T095705Z-bank-day-load.json`; the intentionally
interrupted second diagnostic is `output/task-runs/20260716T123231Z-bank-day-load.json`.
Fresh 100,000-transaction runtime evidence remains required before issue `#795` can move to
fixed-local.

## Documentation Decision

Repository context and the bank-day runbook change because the temporal replay invariant changed.
No public OpenAPI or authored wiki contract changes.
