# CR-1674: Carry-Forward Aggregation Restaging

## Scope

This review covers the terminal-state extension recorded by CR-1673 and GitHub issue #714. The
risk unit is position-timeseries materialization whose changed security state carries across
portfolio aggregation dates that were created by another security.

## Finding

Exact-date aggregation staging correctly rearmed the materialized security's snapshot dates, and
CR-1673 made stale `PENDING` work claimable at the authoritative collective epoch. An existing
portfolio day between two snapshots could still remain `COMPLETE` or `FAILED`, however, because
that carry-forward day is not a snapshot date for the changed security and therefore is not staged
again. The same omission also affected already-`PENDING` source identity and a concurrently
`PROCESSING` claim: ignoring those rows could let completion evidence retain an older source
revision.

Scanning every historical terminal row from the claim loop would be unbounded and would place
repair work in the wrong owner. The affected interval is known while the position materializer is
already propagating changed source state.

## Correction

`MaterializePositionTimeseries` now returns the first convergence or unprocessed snapshot date as
the exclusive end of the changed carry-forward interval. After exact changed dates use the
existing idempotent insert/upsert path, the application calls one repository port to restage only
existing portfolio aggregation jobs inside that portfolio/date interval. Exact materialized dates
are excluded so their source revision advances once.

The set-based PostgreSQL update:

- advances `target_epoch` monotonically and increments `source_revision` for every affected
  existing row;
- returns `COMPLETE`, `FAILED`, and existing `PENDING` rows to `PENDING`;
- preserves a `PROCESSING` lease and marks it `REPROCESS_REQUESTED`, allowing the established
  claim-owned terminal fence to requeue superseded work;
- clears terminal failure evidence only when the row is no longer terminal;
- updates trusted correlation identity when supplied and preserves existing missing-correlation
  diagnostics otherwise;
- counts affected rows from the update result without returning every queue identifier;
- uses the existing portfolio/date and aggregation-date indexes and introduces no schema or
  migration.

Unavailable valuation follows the same fail-closed rule. The current date and directly dependent
next snapshot remain the explicit invalidation set, while existing portfolio jobs are restaged up
to the next unaffected snapshot boundary. With no later boundary, the domain interval is
open-ended but the operation remains limited to already-existing rows for one portfolio after the
changed date.

## Same-Pattern Review

The review covered:

- higher-epoch materialization;
- same-epoch source refresh and duplicate delivery;
- unavailable-valuation invalidation;
- dependent-day convergence and command truncation;
- `PENDING`, leased `PROCESSING`, `COMPLETE`, and `FAILED` rows;
- exact-date double revision, correlation diagnostics, and active lease preservation;
- all callers of aggregation staging and all derived-state repository status transitions.

No second materialization path or duplicate carry-forward repair implementation remains.

## Performance Evidence

The PostgreSQL integration proof adds 2,000 unrelated queue rows, updates a 30-day bounded cohort
with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, and asserts an index-backed plan with no sequential
scan. The observed plan used `ix_portfolio_aggregation_jobs_aggregation_date`; the existing unique
`(portfolio_id, aggregation_date)` index is also accepted because either plan remains bounded by
the same predicates. The product behavior proof updates six mixed-state rows and verifies that
only dates before the convergence boundary move.

## Compatibility And Documentation Decision

No runtime topology, Kafka topic/group/key, partition count, timeout, API, OpenAPI, calculation,
event schema, or database schema changes. Repository context and this review ledger change because
durable source-revision staging behavior changed. README, authored wiki, operator runbook, central
platform context, and Lotus skills are explicit no-change: their existing guidance already requires
bounded source fencing, same-pattern proof, issue evidence, and exact-main closure.

## Validation

- warning-strict application and repository unit tests: `32 passed`;
- PostgreSQL same-epoch, higher-epoch, mixed-status, lease-preservation, convergence-boundary, and
  representative query-plan tests: `2 passed`;
- complete affected PostgreSQL repository module: `9 passed`;
- touched Ruff lint and format plus diff hygiene: passed;
- configured MyPy across `240` sources, complete derived-state unit package (`132 passed`),
  architecture/docs gates, full-repository Ruff, and diff hygiene: passed;
- protected PR validation and exact-main proof: pending before closure.
