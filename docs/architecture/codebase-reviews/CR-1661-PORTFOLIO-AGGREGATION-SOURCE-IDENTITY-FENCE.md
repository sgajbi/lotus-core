# CR-1661: Portfolio Aggregation Source-Identity Fence

## Objective

Make portfolio aggregation deterministic across same-day correction and restatement epochs without
changing the portfolio/date queue grain. The job must retain the exact source identity that made it
eligible, and terminal writes must prove that identity is still current.

## Finding

`MaterializePositionTimeseries` held the authoritative snapshot epoch but
`TimeseriesGenerationRepository.stage_aggregation_jobs` persisted only portfolio, date, status, and
correlation diagnostics. `MaterializePortfolioTimeseries` later queried the portfolio's current
epoch, so the calculation target was schedule-dependent rather than claim-owned.

Lease tokens prevented one worker from finalizing another worker's claim, but did not prevent the
same owned claim from finalizing after newer source material superseded it. Exact-main Main
Releasability run `30428176185` demonstrated the resulting risk: the day-one amount was correct,
while epoch-currentness remained `restated` / `STALE` until the E2E deadline.

## Implemented Boundary

1. `portfolio_aggregation_jobs.target_epoch` records the highest authoritative source epoch staged
   for the portfolio day.
2. `source_revision` advances for each material staging update that changes pending work or
   supersedes/rearms claimed or terminal work.
3. The migration backfills existing target epochs from portfolio-owned `position_state` so queued
   work does not regress to epoch zero during deployment.
4. Claims carry both fields through the framework-free domain model and application command.
5. Eligibility requires authoritative snapshots at or below the staged epoch and remains blocked
   when a newer authoritative snapshot exists without a matching staging update.
6. Calculation uses the claim-owned target epoch. The obsolete execution-time current-epoch query
   and its persistence surface were removed.
7. Success and failure terminal writes compare lease token, target epoch, source revision, and the
   absence of a newer authoritative snapshot. Superseded work returns to `PENDING` instead of
   publishing or failing the current job, including when a snapshot is committed before its
   position-timeseries staging update.
8. A zero-row terminal write rechecks supersession before reporting lost ownership, closing the
   interleaving where newer identity becomes durable between the initial requeue check and terminal
   update.
9. The existing single PostgreSQL upsert remains the staging hot path. Returned durable state
   increments the existing control-queue metric with `new`, `rearmed`, `superseded`, or `no_op`.

## Same-Pattern Review

The agreed scan covered aggregation staging, claim, processor command mapping, calculation,
success/failure terminal writes, lease recovery, reconciliation completion, and analytics
currentness.

- Aggregation success and failure shared the missing source-identity fence and were both fixed.
- Lease recovery already rechecks status and expiry at the write boundary; it carries forward the
  latest persisted target/revision and needs no separate epoch predicate.
- Reconciliation already consumes the completed epoch plus positive `aggregation_revision` and
  rejects older or duplicate revisions.
- Analytics currentness consumes portfolio/position epoch and reconciliation evidence; it does not
  own aggregation queue identity.
- No second aggregation-job implementation or legacy Kafka aggregation-command path exists.

## Compatibility And Evidence Boundary

The migration is additive and reversible. Route/OpenAPI shapes, Kafka topics and groups, event
payloads, partition counts, aggregation arithmetic, correlation diagnostics, reconciliation
revision semantics, timeouts, and the one-deployable derived-state topology are unchanged.

No CI workflow or new gate is warranted: existing repository-native unit, integration, migration,
E2E, and release lanes own the regression. Platform skill/context changes are unnecessary because
the reusable rule is repository-specific and is recorded in repository context. Wiki source changes
because operator interpretation of aggregation staging metrics and job identity changed.

## Evidence

- focused warning-strict unit proof: 118 passed before review and 25 repository tests passed after
  the review fix-forward;
- repository-native MyPy: 240 source files, zero issues;
- Ruff lint and formatting: passed;
- Alembic heads: exactly `c127b2c3d500`;
- exact-branch, fresh-image PostgreSQL rollover proof:
  `test_newer_epoch_supersedes_claim_and_rearms_same_portfolio_day`, 1 passed in 95.95 seconds;
- review fix-forward proof now commits the newer snapshot independently before staging and verifies
  that the old claim is requeued rather than completed;
- full aggregation repository integration proof: 5 passed in 75.01 seconds;
- timeseries contract E2E proof: 4 passed in 77.65 seconds;
- no test timeout, assertion, partition, debounce, topology, or lock-order change.

Remaining proof is protected PR review and final-head CI, exact-main validation, wiki
publication/parity, issue evidence, and branch/worktree reconciliation.
