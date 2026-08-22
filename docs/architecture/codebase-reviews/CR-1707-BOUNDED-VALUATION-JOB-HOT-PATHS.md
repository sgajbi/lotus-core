# CR-1707 - Bounded Valuation Job Hot Paths

Date: 2026-08-22
Status: Fixed locally; protected PR, exact-main validation, and issue closure pending
Issues: #985, #987

## Finding

The governed database hot-path evidence retained two valuation-job findings at 10,000 rows. The
claim update examined 21,001 rows and sequentially scanned `portfolio_valuation_jobs`; stale lease
selection examined 13,000 rows and used the same broad scan. The reset update itself was already
bounded and primary-key indexed.

## Resolution

1. Claim selection resolves only the latest epoch for each portfolio/security/date identity, locks
   at most the governed 1,000-row cohort with `FOR UPDATE SKIP LOCKED`, aggregates those locked ids
   into one typed PostgreSQL array, and updates the target through primary-key `ANY` lookup. This
   preserves ordering, newer-epoch exclusion, readiness-outbox fencing, lease assignment, and one
   caller-owned transaction.
2. Stale recovery now selects an expiry/id ordered cohort of at most 1,000 rows with `FOR UPDATE
   SKIP LOCKED`. Two recovery transactions can therefore own disjoint cohorts without waiting for
   each other or overwriting a terminal writer.
3. The expiry-only partial index is replaced by a partial `(valuation_lease_expires_at, id)` index
   for `PROCESSING` rows. Upgrade and downgrade create the replacement before dropping the
   superseded index, using PostgreSQL concurrent index operations outside the migration
   transaction so the hot writer table is not blocked by an index build.
4. Existing chunked, predicate-rechecked reset/fail/supersede updates remain unchanged. Repository
   methods still stage work only; the scheduler-owned unit of work retains commit and rollback
   authority.

## Measured Result

`make database-hot-path-evidence` at signed production-query SHA `b73b47960` completed seven real
PostgreSQL producer nodes in 74.68 seconds. The unchanged versioned catalog reported:

| Scenario | Before | After | Result |
| --- | ---: | ---: | --- |
| valuation job claim | 21,001 examined, sequential scan | 9,001 examined | 1,000 rows; indexed; no `Seq Scan` or `WindowAgg` |
| valuation stale scan | 13,000 examined, sequential scan | 3,000 examined | 1,000 rows; indexed; no `Seq Scan` or `WindowAgg` |
| valuation stale reset | 2,000 examined | 2,000 examined | 1,000 rows; primary-key indexed |

The report-only artifact contains twelve scenarios and content identity
`sha256:aba3b5b3b889967a198c6741f98c47dc6f9158777491dc23eaaf4428227ce704`.
Its remaining failed posture belongs only to the already routed #506 and #988 families; this slice
does not weaken their budgets or claim their closure.

## Concurrency And Recovery Evidence

- Two real PostgreSQL recovery workers drain 1,001 expired jobs in disjoint cohorts, each bounded
  to 1,000, and converge to exactly 1,001 `PENDING` rows.
- A terminal writer holding the target row lock is skipped by recovery under a 15-second hang
  fence; its committed `COMPLETE` state remains durable.
- Rolling back a staged stale recovery preserves the original `PROCESSING` status, attempt count,
  lease owner, opaque claim token, and expiry.
- Existing two-claimer tests still prove one durable claim per job, the shared in-flight ceiling,
  and newer-epoch exclusion.
- Real PostgreSQL downgrade/upgrade proof replaces and restores the partial indexes and leaves the
  head index present. The Alembic single-head SQL contract also passes.

## Compatibility

This is an internal query, lock, and index-shape change. Repository method signatures, scheduler
cadence, lease/token semantics, readiness-outbox authority, status transitions, API/OpenAPI,
events/Kafka, calculations, dependencies, images, datastores, and topology are unchanged. The
schema migration changes only index metadata and is reversible; it does not change stored rows.

## Same-Pattern And Governance Decision

#988 remains the distinct owner for `reprocessing_jobs` duplicate normalization, and #506 remains
the transaction-ledger page owner. #508 retains broader index-audit work; the obsolete valuation
lease index is replaced rather than duplicated here. #794/#795 retain outbox and capacity work.
No public or operator command changed, so README, RFC, OpenAPI, supported-feature, and authored wiki
source do not change. Existing backend and database-evidence governance already encode the reusable
bounded-query and caller-owned transaction rules, so no central platform context or skill change is
needed.

## Validation Evidence

- Focused query/model/migration unit proof: 91 passed.
- Stale recovery concurrency, terminal-writer, and rollback PostgreSQL proof: 3 passed in 85.28s.
- Claim concurrency, capacity, and epoch-fencing PostgreSQL proof: 3 passed in 80.77s.
- Online index downgrade/upgrade PostgreSQL proof: 1 passed in 86.25s.
- Alembic single-head SQL migration contract: passed.
- Protected PR, exact-main, final independent review, and issue closure evidence remain pending.
