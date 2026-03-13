# CR-174: Control Queue Observability Contract Review

## Scope

- valuation queue
- aggregation queue
- replay (`RESET_WATERMARKS`) queue
- scheduler / worker observability
- operator dashboard and runbook alignment

## Finding

`outbox_events` already exposed first-class gauges for:

- pending rows
- terminal failed rows
- oldest pending age

The durable control queues did not.

That left valuation, aggregation, and replay backlog pressure partially visible only through:

- claim / completion / failure rates
- support API drill-down
- logs

For a banking-grade control plane, that is not enough. Operators need direct visibility into:

1. how many queue rows are still pending
2. how many rows have already failed terminally
3. how old the oldest pending row is

Without those signals, a queue can look quiet in rate charts while still being unhealthy in durable state.

## Decision

Introduce one reusable queue metric family rather than bespoke gauges per queue:

- `control_queue_pending{queue=...}`
- `control_queue_failed_stored{queue=...}`
- `control_queue_oldest_pending_age_seconds{queue=...}`

Queue labels currently used:

- `valuation`
- `aggregation`
- `reprocessing`

This keeps the contract modular and reusable while avoiding another parallel metric namespace per queue type.

## Implementation

Added reusable gauges in:

- `src/libs/portfolio-common/portfolio_common/monitoring.py`

Added durable queue stats repository methods in:

- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py`
- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`

Wired runtime publication in:

- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- `src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py`
- `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`

Surfaced the signals in:

- `grafana/dashboards/portfolio_analytics.json`
- `docs/operations/Grafana-Dashboard-Guide.md`

## Test Coverage

Lower-level proof was added for:

- valuation scheduler queue metric publication
- aggregation scheduler queue metric publication
- replay worker queue metric publication
- valuation queue stats repository contract
- aggregation queue stats repository contract
- replay queue stats repository contract

The tests are unit-level by design because the runtime value here is the scheduler/worker contract, not another full-stack revalidation of Prometheus scraping.

## Result

Durable control queues now have the same first-class observability contract as outbox:

- pending volume
- terminal failed residue
- oldest pending age

This closes a meaningful blind spot in the control plane and makes replay, valuation, and aggregation backlog states directly operable.
