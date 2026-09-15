# CR-1727: Cashflow Economic Context and UTC Calendar Proof

## Scope and status

Review date: 2026-09-16. Owner: Core Codex `/root`. Status: `In Review`.
Owning issues: [#1116](https://github.com/sgajbi/lotus-core/issues/1116) and
[#1041](https://github.com/sgajbi/lotus-core/issues/1041).
Delivery: [PR #1125](https://github.com/sgajbi/lotus-core/pull/1125), based on
`d34fb43f223edd97f6beb2bedaf935545898a568`.
Control classes: persistence/performance, testing/CI, data/methodology and documentation/evidence.

This is a bounded acceptance-proof review, not a new runtime capability or a
repository-wide sign-off. The existing review playbook remains applicable.

## Findings and action

- Test gap: the supported portfolio currency-upsert test asserted the pure common
  cut but did not compare the movement and projection responses that consumed it.
  The existing regression now reads both registered Query routes against real
  PostgreSQL before and after a USD-to-EUR persistence upsert. Identical reads
  retain entire responses, common per-state identity, exact durable generation
  time and empty-window truth; currency changes alter both cuts/content hashes.
- Test gap: the UTC settlement regression covered an ordinary midnight only.
  It now covers month rollover, leap day, year rollover and both DST transitions
  under UTC, Asia/Singapore and America/New_York sessions. Actual PostgreSQL
  offset extraction proves that the DST scenarios exercise real transitions.
  Trade start/end/as-of selection and count queries have separate boundary facts;
  later settlement must not be substituted for the trade instant, or vice versa.
  Exact row identities, instants, amounts, counts and the USD20 settlement total
  are independent expectations, not values computed by production date helpers.
- Diagnostic classification: initial whole-response replay differed only in
  automatically generated correlation IDs. Supplying the supported caller
  correlation header makes requests comparable without altering source chronology,
  freezing time or normalizing away meaningful response fields.
- Proven performance fault: the bank-day fixture's async ORM mapping list issued
  one physical statement per row. A real refresh counter observed43 refreshes for
  21 rows instead of3. Explicit 1,000-row multi-VALUES statements preserve all
  100,000 financial facts and the original5,000-row commit batches without disabling
  maintenance or locks. Both single and cross-physical-batch counters are enforced.
- Proven production SQL fault: the installed refresh statement joined selected
  cashflows back to their own digest rows. Real `EXPLAIN ANALYZE` measured2,012,026
  tuples of work for1,001 rows. Corrective c170 carries chronology beside the digest
  and aggregates those rows directly; measured work is7,023. Digest JSON fields,
  canonical ordering, UTC normalization and durable parent locks are unchanged.
- Selection gap: the currency/common-product regressions were selected by the
  query-authority and lifecycle lanes, but were absent from bounded critical
  coverage. The earlier assertion that all three already selected them was wrong.
  This PR explicitly adds both product regressions and physical/actual SQL work
  guards to the bounded manifest. Migration proof remains explicitly selected.
- Full-integration finding: three full-only OpenAPI assertions still pinned the
  obsolete response-serving timestamp and baseline-epoch descriptions. Published
  source-materialization and collective reconciliation descriptions are correct;
  production contracts remain unchanged. The tests now independently pin those
  descriptions and preserve all adjacent field, authority and response checks.
  The existing premerge operations lane explicitly selects the three regressions
  and three served-schema mutations that the same registered-route guards reject.
- Runtime-classification fault: searching whole pytest nodeids interpreted integration
  paths in parameter IDs as database-runtime authority. Ordinary unit selection executed
  only25 of41 manifest guards, excluding16 newly added membership/omission cases.
  Classification now uses only the test-file portion, retaining actual integration/E2E
  paths and explicit database markers. No selector or threshold was relaxed.
- Final-head review: the bank-day logging wrapper now discards cached PostgreSQL
  plans after renaming/installing the function, following the existing migration
  counter's practice. Both count cases deliberately warm source triggers on the
  same backend before installation; rollback removes only warmup fixture facts.
- Native unit finding: a source-provenance test assumed automatic user-site
  discovery, disabled by the pinned venv. Its real foreign package is now placed
  on the inherited search path; an unguarded subprocess must actually import it
  before the unchanged repository launcher must reject it. No test is skipped
  and no source-provenance guard is weakened.

## Executed developer evidence

The strengthened currency route test is selected by the native query-authority
and lifecycle lanes; this corrective PR also adds it to bounded critical coverage.
The UTC test retains its lifecycle marker. The earlier calendar-only lifecycle85
receipt below predates the added work and corrective-migration cases.

- Native `make test-query-authority-db-contract`: 5 passed in 52.93s.
- Representative temporary mutation forced only projection's cut context back to
  USD after the EUR update. The actual SQL/routes returned both EUR currencies,
  but the new cross-product identity assertion rejected the wrong cut:
  1 failed / 4 passed in 52.22s, native exit2. An explicit wrapper verified this
  exact intended failure and exited0. The mutation was completely removed;
  restored native lane: 5 passed in 52.84s.
- Expanded settlement calendar pack: native `make test-critical-lifecycle-db`,
  85 passed / 1209 intentionally deselected in 374.54s, exit0. One existing
  ingestion deprecation warning; no new skips or relaxed gates.
- Restored complete trade/settlement/calendar lane: native
  `make test-critical-lifecycle-db`, 85 passed / 1209 intentionally deselected
  in 377.07s, exit0; the same single existing ingestion deprecation warning.
  This includes both product currency reads, supported persistence currency
  changes, migration and retained aggregation/rollback controls.
- Full native `make lint` passed after the trade-window extension;
  `make quality-wiki-docs-gate` passed with the new review entry tracked.
- Lock-backed Windows Python3.11.9 diagnostic: unchanged100,000-row capacity test
  and both physical refresh counters,3 passed/398.25s; ledger query2.922s.
  The rowwise mutation was rejected (43 versus3 refreshes for21 facts).
- Old installed refresh: actual-work guard failed at2,012,026 tuples/1,001 rows,
  with unchanged currency, digests, chronology, counts and independent cash total.
  The first combined migration/work run reused a cached old migration image and
  correctly remained red; it is not corrective-head proof. Rebuilt-image focused
  pack:5 passed/86.89s, work7,023, unchanged full source-cut rows, real nonempty
  Alembic upgrade/downgrade/no-op replay, transactional DDL rollback and retained
  backfill/timezone/late-writer/move/atomic maintenance controls. Final aggregate
  lanes remain required.
- SQL migration/manifest units:33 passed/1.04s on pinned Windows Python3.11.9.
  Changed historical rewrite premises are rejected; generated SQL alone is not
  migration acceptance.
- Final manifest guard pack:37 passed/0.67s, including representative omissions
  of each required product/work proof rejected by the actual membership guard.
  Native manifest collection selects174 bounded critical database cases and
  89/1298 lifecycle cases (1209 intentional deselections). Collection is not
  execution. Native full lint, mypy329, heads/history inventory, documentation
  gates and live comparison of all38 required checks passed with this correction.
- Final-head review distinguished historical c169 backfill/fence execution from
  installed-c170 proof. The corrective regression now also forces the actual
  c170 late-writer lock ordering, key-share-compatible insert, move/delete with
  independent per-root USD102/USD202 facts and overlapping ordered bulk writes.
  Revised real PostgreSQL migration module:2 passed/51.97s on pinned Python3.11.9.
- Complete native Full diagnostic:3 failed/1295 passed/one existing warning in
  2935.55s, native Make exit1. All failures were the stale OpenAPI assertions above;
  the result remains failed, not a certificate. JUnit SHA256
  `fdf807c66c7bbdcab16ea64c0fe24573e201164271a0efa59f80da7477daf854`.
  Exact owned project `lotus-integration-integration-all-8898ca8e` completed normal
  teardown; container, volume and network label filters were empty afterwards.
- Corrected native `make test-ops-contract`:330 passed/11.20s, exit0 on pinned
  Windows Python3.11.9. All three corrected guards first accept the real published
  schema, then reject one-field description mutations through `/openapi.json`;
  a deep copy prevents shared-cache mutation. Migration/manifest units45 passed/
  0.56s, including omission mutations for each newly required metadata guard.
  This fixes all three observed failures without treating the earlier1295 passing
  cases as a new complete aggregate. Renewed final-head CI and exact-main Full
  remain required.

Developer executions are not final-head or merged-main GitHub receipts. The final
PR and source manifests must identify the exact signed head, landed SHA, producing
commands/jobs and terminal conclusions before source closure is claimed.

### Runtime selection correction and isolated producer proof

- Eight neutral-ID runtime controls first reproduced the classifier fault under the
  ordinary unit selector:5 failed/6 passed/0.46s, native exit1. Corrected classifier:
  runtime plus manifest guards52 passed/0.41s, exit0; all41 manifest cases selected,
  compared with25 before the correction. Actual integration/E2E file and explicit
  database-marker controls still pass. Native test-lane governance guard passed.
- Existing isolated Core seed producer session64858 exited0 on clean signed
  `89cb4e88aad2cc832316200e2056a53d387a0056`, unchanged through teardown. Fresh
  supported ingestion produced31 transactions/11 valued positions, COMPLETE quality,
  all four readiness domains READY/no blockers across three stable API/independent
  PostgreSQL observations. Aggregation278/valuation3045 complete; all terminal
  pending/processing/failed jobs, outbox backlog and contention0. Exact source images
  are branch-qualified, not new merged-main release or consumer acceptance.
  Proof SHA256 `408cd32b608596ef21b4bea7fd969a40527e3c081b33aac0f82a3ef9ee39945c`;
  [verified runtime receipt](https://github.com/sgajbi/lotus-core/issues/714#issuecomment-5691022629).
  Owned project `lotus-e2e-issue-799-fresh-canonical-e1599ea5` normal teardown;
  exact resource filters empty and retained app-local identity unchanged.
- Complete native ordinary units initially1 failed/9919 passed/3 platform-dependent
  skips/16 intentional deselections in502.25s, Make1. The sole failure was the
  unreachable user-site fixture above, not financial or PostgreSQL behavior.
  Corrected source-provenance/runtime/migration/manifest pack65 passed/2.52s,
  exit0. Both actual PostgreSQL warm-backend count cases passed/43.63s after
  explicit plan discard. The first warmup-only run also passed/46.92s; it did
  not reproduce nondeterministic stale-plan binding and is not claimed as RED.
  The existing rowwise43-versus3 mutation remains the behavioral bad-work proof.
- Corrected complete native ordinary units:9920 passed/3 unchanged Windows image
  mode/symlink skips/16 intentional database-runtime deselections in485.27s, exit0.
  Warmed counter's memory-only rowwise mutation again fails at43 refreshes versus3
  for21 facts/34.47s, native1 verified wrapper0; tracked source remains unchanged.
  Restored normal real PostgreSQL migration/counter/installed-work pack5 passed/
  64.91s, exit0. Native full lint/mypy329/docs and ops330 passed/11.17s.

## Ownership, adjacent scan and no-change decisions

Source production behavior remains owned by the existing admission, application,
domain cut builder and PostgreSQL repositories. Tests borrow the fixture engine;
each HTTP request owns/closes its session and the test owns/closes its client.
No shared provider is disposed. Portfolio currency is changed through
`PortfolioRepository.create_or_update_portfolio(PortfolioEvent)`, not a direct ORM
currency write. This is not a Kafka/HTTP ingestion runtime receipt.

The adjacent scan covered the common-cut builder and both product services,
the supported portfolio persistence update regression, transaction window
predicates and settlement grouping, plus their actual premerge manifest selection.
The adjacent scan identified the installed-refresh self-join; c170 is the bounded
source correction rather than rewriting applied c169 history. Historical migration
tests restore their captured installed function so legacy proof cannot leak old SQL
into subsequent current-head work tests. Existing source-restatement, foreign-tenant,
timezone/materialization, move, insert/update/delete and aggregation rollback controls
remain selected; no claim is made about unreviewed APIs.

Function-only corrective migration and test-manifest changes; no table/schema,
financial calculation, API/DTO/contract shape, lock-backed dependency, workflow,
source chronology or runtime-topology changes. Typed
tenant and deliberately global reference scope, snapshot ordering, aggregation
and rollback fences are preserved. No IAM grant or timezone authority is invented.
The migration contract, repository-local practice and Validation-and-CI wiki source
are updated for actual execution, selected proof and fresh migration images.
Publish changed wiki source after merge and verify committed-blob parity. README,
OpenAPI/DTOs, financial methodology, central Platform context/routing and skills need
no change: authority and contract behavior are unchanged and existing controls
already require premise validation, real database proof and truthful source receipts.

## Remaining acceptance

Require amended final-head review and all required checks, approved signed-feature
linear merge, exact merged-main including Integration Full and delivered-only
branch hygiene. Keep #1116 open until source delivery is verified. Idea #1320 owns
independent accepted-then-replayed durable evidence after governed reconstruction;
Core unit/CI/fixture proof cannot substitute for it. No release, full-stack,
production or broader #714 completion is claimed here.
