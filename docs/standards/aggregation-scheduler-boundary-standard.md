# Aggregation Scheduler Boundary Standard

Portfolio aggregation uses the durable `portfolio_aggregation_jobs` queue directly. The scheduler
must keep lease policy, repository access, bounded processing, metrics, clocks, and token generation
behind explicit in-process ports. It must not publish a same-owner Kafka command.

## Responsibilities

`portfolio_aggregation_service.app.application.aggregation_jobs.scheduler` owns:

1. poll-loop and shutdown orchestration,
2. expired-lease recovery invocation,
3. deterministic eligible-job claim invocation,
4. UTC lease-expiry construction,
5. queue metric update orchestration,
6. handoff to the bounded job processor.

`portfolio_aggregation_service.app.application.aggregation_jobs.processor` owns:

1. fixed worker concurrency,
2. lease-bearing materialization command mapping,
3. per-job unexpected-failure isolation,
4. typed batch outcome accounting.

`portfolio_aggregation_service.app.ports.aggregation_scheduler_ports` owns repository-provider,
repository, metrics-sink, clock, token-generator, and batch-processor contracts.

`portfolio_aggregation_service.app.infrastructure.aggregation_scheduler_adapters` owns concrete
SQLAlchemy session/repository, Prometheus metric, and system-clock adapters. Runtime composition owns
the UUID token generator and service-instance lease owner.

## Boundary Rules

The scheduler and processor must not import database session factories, concrete repositories,
Kafka producer/consumer APIs, direct publish/flush calls, or raw Prometheus metric functions.

Claims must use `FOR UPDATE SKIP LOCKED`, persist owner/token/UTC expiry, and increment the attempt
count in the claim transaction. Completion, requeue, and failure writes must match job id plus lease
token and clear all lease fields. Expiry recovery must recheck `lease_expires_at` on the write so a
renewed or reclaimed job cannot be overwritten by stale work.

One poll may claim only the configured batch size. Processing concurrency must remain bounded by
`PORTFOLIO_AGGREGATION_WORKER_COUNT`; it must not create an unbounded in-memory backlog.

## Enforcement

`make architecture-guard` runs `scripts/quality/aggregation_scheduler_boundary_guard.py`. Package
ownership tests prevent restoration of the retired consumer, publisher, `app/core` scheduler, and
consumer-manager paths.

## Compatibility

Portfolio-timeseries arithmetic, durable queue identity, completion and reconciliation events,
outbox atomicity, query APIs, and downstream payloads remain unchanged. The intentionally removed
internal contract is `portfolio_day.aggregation.job.requested`; it had no external producer or
consumer and duplicated the durable database queue within one deployable.
