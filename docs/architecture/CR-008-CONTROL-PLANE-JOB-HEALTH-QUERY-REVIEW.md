# CR-008 Control-Plane Job Health Query Review

## Scope

Review the query shape and index alignment for control-plane backlog / health views:

- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- job tables in `src/libs/portfolio-common/portfolio_common/database_models.py`

This review explicitly excludes worker claim paths such as:

- `find_and_claim_eligible_jobs(...)`
- `FOR UPDATE SKIP LOCKED` scheduler queries

Those are runtime-critical and were reviewed separately.

## Findings

### 1. The main issue was query fan-out, not missing worker indexes

The support/control-plane surface was issuing many separate aggregate queries over the
same two job tables:

- `portfolio_valuation_jobs`
- `portfolio_aggregation_jobs`

Examples included:

- pending count
- processing count
- stale-processing count
- failed count
- failed-in-window count
- oldest open business date

These were being fetched as independent queries even when rendered as one overview or SLO view.

Operational implication:

- not a correctness bug
- not a worker-throughput bottleneck
- but unnecessary database round-trips and duplicated query logic on an operator-facing path

### 2. Existing table indexing is broadly adequate for the current query family

The job tables already expose the main filter columns as indexed fields:

- `portfolio_id`
- `status`
- date columns:
  - `valuation_date`
  - `aggregation_date`

The current review did **not** find evidence that the immediate problem required a schema/index migration.

The main inefficiency was:

- repeated scans/round-trips for related aggregates

not:

- obviously missing index coverage on the queried predicates

### 3. Support-path optimization should not be confused with worker-path tuning

The worker claim repositories and job schedulers are a different class of performance concern.
They need:

- concurrency correctness
- deterministic claiming
- low-latency lock behavior

The control-plane overview/SLO endpoints need:

- fewer aggregate queries
- lower operational load
- simpler maintenance

Those two concerns should stay separate in review and refactor planning.

## Action taken

Implemented control-plane consolidation:

- added combined health-summary queries for:
  - valuation jobs
  - aggregation jobs
- updated `OperationsService` to use those summaries instead of many point queries
- added unit coverage for:
  - summary-query compilation and mapping
  - service behavior on the new summary-returning interface

This reduces support-path query fan-out without changing API behavior.

## Recommendation

1. Keep using combined summary queries for operator/SLO views.
2. Do **not** add indexes speculatively without evidence from execution plans or hosted runtime metrics.
3. Review worker claim paths separately under a scheduler/backlog review batch if they become a bottleneck.

## Sign-off state

Current state: `Hardened`

Reason:

- the identified control-plane query debt has been removed
- no immediate schema/index change is justified by current evidence
