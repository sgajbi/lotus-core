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
   transaction so the hot writer table is not blocked by an index build. The migration inspects
   PostgreSQL catalog validity and both the replacement and superseded governed definitions before
   acting: a valid partial replacement is resumed, an invalid interrupted concurrent build is
   dropped and rebuilt, and a conflicting same-name index fails source-safely instead of being
   silently accepted or removed.
4. Existing chunked, predicate-rechecked reset/fail/supersede updates remain unchanged. Repository
   methods still stage work only; the scheduler-owned unit of work retains commit and rollback
   authority.
5. The 1,000-row claim cohort is now shared runtime authority rather than a repository-only clamp.
   The dispatch coordinator uses it for both repository calls and exhaustion detection, while the
   ingestion operating policy and Query Control Plane capacity projection expose the same effective
   value. A legacy configured value above 1,000 remains startup-compatible but no longer causes an
   early dispatch-loop stop or optimistic poll-capacity report.

## Measured Result

`make database-hot-path-evidence` at exact clean signed review-fix SHA `f5dc3e234` completed seven
real PostgreSQL producer nodes in 85.93 seconds. The unchanged versioned catalog reported:

| Scenario | Before | After | Result |
| --- | ---: | ---: | --- |
| valuation job claim | 21,001 examined, sequential scan | 9,001 examined | 1,000 rows; indexed; no `Seq Scan` or `WindowAgg` |
| valuation stale scan | 13,000 examined, sequential scan | 3,000 examined | 1,000 rows; indexed; no `Seq Scan` or `WindowAgg` |
| valuation stale reset | 2,000 examined | 2,000 examined | 1,000 rows; primary-key indexed |

The report-only artifact contains twelve scenarios and content identity
`sha256:f3810fb8984fedb45e10c9f05457bcefca028e35476f6c4f40dceb5e4f2f3f5a`.
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
- Real PostgreSQL downgrade/upgrade proof replaces and restores the partial indexes, then simulates
  interruption after the replacement was created but before the old index was removed. A retry
  recognizes the valid replacement, removes the superseded index, and leaves the head index
  present. Unit proofs cover invalid-build repair and conflicting-definition rejection. The
  Alembic single-head SQL contract also passes.

## Compatibility

This is an internal query, lock, and index-shape change. Repository method signatures, scheduler
cadence, lease/token semantics, readiness-outbox authority, status transitions, API payload shapes,
events/Kafka, calculations, dependencies, images, datastores, and topology are unchanged. OpenAPI
descriptions and the ingestion operating-policy maximum now state the effective 1,000-row physical
claim boundary. The schema migration changes only index metadata and is reversible; it does not
change stored rows.

## Same-Pattern And Governance Decision

#988 remains the distinct owner for `reprocessing_jobs` duplicate normalization, and #506 remains
the transaction-ledger page owner. #508 retains broader index-audit work; the obsolete valuation
lease index is replaced rather than duplicated here. #794/#795 retain outbox and capacity work.
No public or operator command changed, so README, RFC, supported-feature, and authored-wiki
navigation surfaces do not change. The operator-visible effective-capacity clarification is
recorded in the OpenAPI descriptions, repository runbook, and authored
`wiki/Operations-Runbook.md`; pre-merge source validation and post-main publication/parity are
required. Existing backend and database-evidence governance already encode the reusable
bounded-query and caller-owned transaction rules, so no central platform context or skill change
is needed.

## Validation Evidence

- Focused query/model/migration unit proof: 91 passed.
- Stale recovery concurrency, terminal-writer, and rollback PostgreSQL proof: 3 passed in 85.28s.
- Claim concurrency, capacity, and epoch-fencing PostgreSQL proof: 3 passed in 80.77s.
- Review-fix oversized claim proof: unit SQL clamps to 1,000; PostgreSQL drains 1,001 as disjoint
  1,000 and 1 cohorts in 90.53s.
- Shared-cohort review proof: an oversized configured batch exposes 1,000 through runtime and
  ingestion settings; a two-round dispatch unit proof processes 1,000 then 1 rather than declaring
  the first full physical cohort exhausted; Query Control Plane OpenAPI describes effective rather
  than configured capacity.
- Complete valuation repository PostgreSQL file: 40 passed in 253.42s.
- Repository-native `test-unit-db`: 18 passed in 113.99s.
- Restart-safe index unit matrix: 5 passed; governed resume, invalid repair, conflicting required
  or superseded definition rejection, and reversible online DDL are covered.
- Online index downgrade/upgrade and interrupted-create replay PostgreSQL proof: 2 passed in 89.71s.
- Alembic single-head SQL migration contract: passed.
- Full lint/security/contract guard chain, MyPy across 318 source files, complete architecture guard,
  documentation evidence pack, architecture catalog, and wiki-source validation: passed.
- The changed `Operations-Runbook.md` passes the platform professional-wiki audit and the
  repository wiki/docs gate after adding an early current-scope, evidence-boundary, and reader map.
- At exact signed implementation head `ac7000b2a`, Remote Feature Lane `32568806213` and Quality
  Baseline `32568807457` passed. PR Merge Gate `32568807448` passed every test and contract job
  before this final documentation-only head. Codex review reported no major issues at that exact
  implementation head, and all three earlier review threads are resolved with linked fix-forward
  evidence.
- Final documentation-head PR validation and review, exact-main validation, authored-wiki
  publication/parity, and issue closure evidence remain pending.
