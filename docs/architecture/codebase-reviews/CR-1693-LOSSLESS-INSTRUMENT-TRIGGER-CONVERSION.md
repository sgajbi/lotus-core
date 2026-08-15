# CR-1693 Lossless Instrument Trigger Conversion

## Objective

Close GitHub issue #488 by making the price-trigger to `RESET_WATERMARKS` job handoff an explicit
repository-owned unit of work and proving that an earlier price update cannot be lost while a
scheduler conversion is in flight.

## Durable Ownership And Invariant

`InstrumentReprocessingConversionRepository` now owns the bounded conversion operation. The
caller retains the transaction boundary; the repository claims and deletes ordered trigger rows
with `FOR UPDATE SKIP LOCKED`, then stages each corresponding reset job before commit.

The existing PostgreSQL constraints remain authoritative:

- trigger UPSERT retains the minimum `earliest_impacted_date` per security;
- one partial unique index permits only one `PENDING` reset job per security;
- pending-job UPSERT retains the minimum impacted date and its correlation lineage;
- a `PROCESSING` job is immutable, so a later trigger creates a separate pending generation; and
- rollback restores the deleted trigger if durable job staging fails.

The job staging adapter now returns `created` or `coalesced_pending` from the exact PostgreSQL
UPSERT result. The coordinator publishes only those bounded outcomes through
`instrument_reprocessing_trigger_conversions_total{outcome}`. No security, portfolio,
correlation, job, or transaction identifier is a metric label.

## Concurrency Evidence

The real-PostgreSQL suite proves:

1. an earlier same-security producer blocks behind the claimed trigger row, then survives as a
   new trigger and coalesces into the pending job on the next conversion;
2. injected staging failure rolls the trigger deletion back and leaves no partial job;
3. repeated conversion converges to one pending job at the earliest date;
4. an already-processing job remains unchanged while an earlier trigger becomes a durable pending
   generation; and
5. `SKIP LOCKED` lets a second converter complete independent-security work while the first
   security is paused.

The suite is included in `critical-db-coverage` and the governed concurrency/duplicate-delivery
test pack.

## Compatibility Impact

No API, OpenAPI, Kafka topic or event shape, reset-job payload, scheduler cadence, valuation
formula, database schema, migration, dependency, container, or runtime topology changed. Existing
pending jobs continue to coalesce. The only intentional internal change is explicit conversion
ownership and truthful outcome telemetry.

## Documentation Decision

The reprocessing flow document and operator wiki now describe durable job conversion, pending
versus processing generation semantics, and the bounded support metric. No README or RFC change is
needed because product capability and external contracts are unchanged.

## Validation Evidence

- exact clean local head `1c262913130cadeaa10b931842eeb4bc00469a62` passed independent
  read-only review with no blockers;
- full unit lane: `8,381 passed, 13 deselected`;
- protected critical-DB lane: `72 passed`;
- final exact-head PostgreSQL conversion suite: `5 passed`;
- MyPy: 318 source files with no issues;
- full lint/governance catalog, architecture, repository-transaction, metric-vocabulary,
  concurrency/duplicate-delivery, no-alias, OpenAPI, API vocabulary/catalog, migration SQL smoke,
  and docs/wiki guards: green; and
- PR, CI, exact-main, wiki publication, and closure evidence remains durable on GitHub issue #488
  rather than being copied into this architecture decision after merge.
