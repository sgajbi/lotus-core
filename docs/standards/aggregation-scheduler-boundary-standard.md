# Aggregation Scheduler Boundary Standard

The portfolio aggregation scheduler must keep polling policy, dispatch planning, repository access,
metrics, clocks, and event publication behind explicit in-process ports.

## Responsibilities

`portfolio_aggregation_service.app.core.aggregation_scheduler` owns:

1. poll-loop orchestration,
2. stale-job reset invocation,
3. eligible-job claiming invocation,
4. queue metric update orchestration,
5. dispatch failure recovery orchestration,
6. stop/sleep behavior.

`portfolio_aggregation_service.app.core.aggregation_job_publisher` owns:

1. aggregation job record-key construction,
2. aggregation job event payload planning,
3. correlation header construction,
4. dispatch plan publication,
5. partial publish failure classification,
6. delivery-confirmation timeout classification.

`portfolio_aggregation_service.app.ports.aggregation_scheduler_ports` owns scheduler repository,
repository-provider, metrics-sink, and clock contracts.

`portfolio_aggregation_service.app.infrastructure.aggregation_scheduler_adapters` owns concrete
SQLAlchemy session/repository, Prometheus metric, and system-clock adapters.

## Boundary Rules

The scheduler must not import database session factories, concrete repositories, concrete Kafka
producer APIs, direct publish or flush calls, or raw Prometheus metric functions.

The scheduler ports must not import database session factories, concrete repositories, concrete
Kafka producer APIs, or runtime global providers.

The event planner/publisher module must not depend on database sessions or concrete repositories.
Kafka producer creation must stay behind the shared `portfolio_common.event_publisher` adapter.

## Enforcement

`make architecture-guard` runs `scripts/aggregation_scheduler_boundary_guard.py`.

## Compatibility

This is an in-process design modularity rule. It preserves `AggregationScheduler()` runtime
construction, Kafka topic, Kafka key, payload shape, correlation header behavior, stale reset
behavior, queue metric names, dispatch recovery behavior, poll cadence, database schema, and runtime
topology.
