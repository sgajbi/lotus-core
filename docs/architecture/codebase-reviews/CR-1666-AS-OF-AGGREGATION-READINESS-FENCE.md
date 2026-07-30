# CR-1666: As-Of Aggregation Readiness Fence

## Objective

Make historical portfolio readiness deterministic without hiding future-dated work from the
default operator queue view.

## Finding

The canonical front-office seed validates portfolio state through a governed report date, but it
consumed the unbounded support overview as a completion gate. Legitimate aggregation jobs after
that date therefore stranded the historical validation even when all in-scope calculations had
converged.

Portfolio readiness attempted to compensate by ignoring the entire aggregation backlog when the
oldest pending job was after the requested date. That inference was not valid for a mixed backlog:
one in-scope row plus later rows could keep future work blocking, while summary counts could not
identify which processing or failed rows were in scope.

## Implemented Boundary

1. The support overview accepts an optional `as_of_date`.
2. The repository aggregation-health query applies
   `portfolio_id` and `aggregation_date <= as_of_date` before deriving pending, processing, stale,
   failed, recent-failure, and oldest-open evidence.
3. Omitting the parameter preserves the full durable queue view.
4. Portfolio readiness passes its requested date, or its resolved latest business date when the
   request omits one, into the same repository-scoped overview and no longer performs oldest-date
   inference.
5. The canonical seed and its failure diagnostics request the bounded overview for their governed
   validation date.

## Same-Pattern Review

The scoped review covered the support overview, portfolio readiness, calculator SLOs, aggregation
job listings, load-run progress, and the canonical seed verifier.

- Calculator SLOs remain intentionally unbounded operational telemetry.
- Aggregation job listings retain exact-date and identity filters for drill-through.
- Load-run progress already owns an explicit target business date.
- Both normal polling and failure diagnostics in the canonical seed now use the same bound.
- No database row, scheduler, claim, retry, or aggregation calculation behavior changes.

## Compatibility

The route parameter is additive. Existing callers that omit it receive the same full-queue counts
and response shape. Bounded callers exclude only aggregation work after the requested business
date; work on or before the date continues to block. Portfolio/tenant ownership, status
classification, stale and failed windows, Kafka contracts, schemas, migrations, calculations, and
runtime topology are unchanged.

## Evidence

- Focused repository, application, router/OpenAPI, readiness-builder, and canonical-seed tests:
  `316 passed`.
- Final focused gates, protected CI, canonical runtime evidence, exact-main validation, and wiki
  publication will be recorded on GitHub issue #856.
