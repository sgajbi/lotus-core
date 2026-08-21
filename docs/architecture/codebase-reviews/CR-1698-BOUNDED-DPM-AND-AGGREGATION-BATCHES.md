# CR-1698: Bounded DPM and Aggregation Batches

Date: 2026-08-21
Issues: #961, #962
Status: Merged and exact-main validated

## Finding

Two caller-sized persistence boundaries remained after CR-1695. QCP accepted unbounded DPM
instrument and FX-pair collections and sent each collection through one price or FX predicate.
Portfolio aggregation selected every expired lease and updated caller-sized identifier sets. Both
paths could exceed a safe PostgreSQL bind/memory envelope, and model-target expansion could make an
otherwise valid readiness request exceed the leaf market-data contract after mandate/model reads.

## Resolution

- Contract-owned DPM constants cap instruments and FX pairs at 1,000 for both direct coverage and
  source-readiness requests; OpenAPI publishes the limits. Currency members now enforce the
  claimed alphabetic ISO 4217 shape and both requests reject duplicate pairs.
- QCP normalizes, deduplicates, globally sorts, and chunks market-price and FX reads through the
  shared 1,000-row/32,000-bind authority. Result ordering and application-owned request ordering
  remain deterministic.
- If caller instruments union model targets exceeds 1,000, readiness performs none of the
  eligibility, tax-lot, or market-data reads. All three families fail closed with
  `DPM_EVALUATED_INSTRUMENT_LIMIT_EXCEEDED`; Core publishes no truncated universe.
- Aggregation recovery locks an ordered 1,000-row expired cohort with `FOR UPDATE SKIP LOCKED`.
  Retry-exhausted and retryable identifiers are disjoint, sorted, deduplicated, and updated through
  shared bind-safe chunks while the scheduler provider retains transaction ownership.

## Evidence

- 74 focused request, policy, adapter, and aggregation unit tests pass; the final changed adapter
  and recovery files contribute 36 passing tests.
- OpenAPI assertions prove `maxItems=1000` on both collections in both public requests.
- Real PostgreSQL maximum-input price and FX reads execute exactly one statement each and return
  all 1,000 records in deterministic order.
- The complete changed DPM and aggregation PostgreSQL pack passes 14 tests in 115.88 seconds. It
  includes maximum-input price/FX reads, 1,001-row backlog draining as 1,000 then 1, and rollback of
  all 1,001 staged updates after an injected second-chunk failure.
- A deterministic two-session PostgreSQL proof holds the first 1,000-row cohort transaction open
  while a second recovery skips those locks and recovers the remaining row: 1 passed in 60.11 seconds.
- A terminal-writer row-lock regression proves recovery uses `SKIP LOCKED`, reports zero work,
  preserves `COMPLETE`, and fails within a 15-second fence if the lock contract regresses: 1 passed
  in 67.98 seconds.
- `make test-unit-db` passes 18 tests in 100.70 seconds. Repository-native lint, type, architecture,
  OpenAPI, API vocabulary, wiki-source, and documentation-evidence gates pass. Independent review
  signed off exact `5edaa7c3925e8df658fbdb43592eaf9ac356d04e` with no blocker.
- PR #977 passed Remote Feature Lane `32448860218` and all 23 Pull Request Merge Gate jobs in
  `32449699217`, then merged by rebase as exact main
  `b9732c56415141b4184a11e18210a66145cf62ef`.
- Main Releasability run `32452388447` passed at that exact main SHA: 24 executable jobs passed,
  the two institutional jobs were expected policy skips, and no job failed or was cancelled.
  Integration Full, combined coverage, exact-source images, Docker smoke, full E2E, fast/full
  performance, latency, and failure recovery all passed.
- Authored wiki publication `8f82f6a` includes the DPM and aggregation updates and strict parity is
  zero. The merged feature branch was tree-equivalent to main before local/remote deletion; Core
  returned to one clean worktree on exact main.

## Compatibility and Boundaries

Supported requests retain their response, evidence, freshness, and content-identity semantics.
Oversized public requests now intentionally receive the standard validation response; source-owned
model expansion fails as readiness `UNAVAILABLE` rather than blaming the caller or truncating.
Aggregation changes only internal recovery query shape and per-cycle counts. There is no database
schema/migration, event/Kafka, calculation, dependency, image, datastore, or topology change.

#972 owns standalone eligibility/tax-lot filters; #976 owns the distinct unbounded model-target
source read before composed readiness can enforce its ceiling. #503 owns reconciliation reads, #719 owns
transaction economics, and #714 owns broader derived-state topology/capacity. Existing platform
governance already mandates contract-owned capacity and repository-owned bind safety, so no central
skill or platform-context change is required.
