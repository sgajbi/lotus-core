# CR-1653: Critical Database Lifecycle Proof

## Objective

Turn the highest-risk persistence and recovery transitions in GitHub issue
[#603](https://github.com/sgajbi/lotus-core/issues/603) into one bounded, blocking DB-direct proof
pack without duplicating broad integration coverage.

## Finding

Existing PostgreSQL tests covered many individual transitions, but their evidence was scattered.
No named lane guaranteed that ingestion idempotency, transaction persistence, outbox claim and
delivery, valuation and aggregation recovery, replay, atomic rollback, and operator projections
remained coherent together. One boundary remained missing: an accepted ingestion job through
durable transaction persistence, exactly one outbox dispatch, retained support lineage, and replay
without duplicate publication.

## Change

1. Added the `lifecycle` marker and `critical-lifecycle-db` manifest with the `integration`
   environment and `db_direct` runtime.
2. Added `make test-critical-lifecycle-db` and protected it in Feature Lane, PR Merge Gate, and
   Main Releasability.
3. Marked 27 exact existing nodes, collecting 30 parameterized cases. Broad modules are not marked.
4. Added one PostgreSQL-backed transaction lifecycle case that asserts job fingerprint and
   lineage, transaction and processed-event identity, pending-to-processed outbox state, one
   publication, cleared claim state, and idempotent replay with no duplicate row or publication.
5. Added manifest, scope, workflow, and lane-contract tests plus repository context and testing
   documentation.

Router fakes contribute API idempotency-contract evidence only; they do not replace the real
database boundary.

## Same-Pattern Scan

The exact selection covers ingestion, persistence, outbox, valuation, skipped-terminal state,
aggregation, replay, operator visibility, concurrency, retry exhaustion, stale-claim fencing, and
atomic rollback. The #602 matrix names this pack as transaction integration evidence while account
and cash integration remain partial under their domain-owning issues #457 and #456.

## Validation

- Exact marker collection: 31 cases.
- Complete DB-direct shard: 31 passed, 876 deselected in 111.88 seconds.
- 52 warning-strict manifest, test-scope, workflow, and lane-governance tests passed.
- Ruff and diff hygiene passed for changed Python files.
- The new cross-boundary proof and its per-test database-session isolation each passed separately.

## Compatibility And Documentation Decision

This adds blocking test evidence and no production API, OpenAPI, event, schema, migration, or
calculation behavior. Repository testing strategy, context, and wiki source change because a new
governed command and lane now exist. Publish the wiki after merge and verify strict parity.
