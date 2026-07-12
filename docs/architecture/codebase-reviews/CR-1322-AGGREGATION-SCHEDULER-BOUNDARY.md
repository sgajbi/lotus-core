# CR-1322 Aggregation Scheduler Boundary

## Scope

Issue cluster: GitHub issue #626.

This slice splits portfolio aggregation scheduler policy from database sessions, concrete
repositories, metric functions, clocks, and Kafka publication.

## Objective

Make aggregation job event planning, dispatch failure classification, stale reset invocation,
eligible-job claiming, queue metric updates, dispatch recovery, and bounded poll behavior
testable without global database sessions, concrete repositories, concrete Kafka producers, or
real Prometheus metric functions.

## Changes

1. Added `aggregation_job_publisher.py` with an aggregation-job publisher port, Kafka adapter over
   `portfolio_common.event_publisher`, pure record-key/header/payload planning, dispatch plans,
   partial publish failure classification, and flush-timeout classification.
2. Added `app/ports/aggregation_scheduler_ports.py` with scheduler repository, repository-provider,
   metrics-sink, and clock ports.
3. Added `app/infrastructure/aggregation_scheduler_adapters.py` with SQLAlchemy repository-provider,
   Prometheus metric-sink, and system-clock adapters.
4. Refactored `AggregationScheduler` to accept injected settings, repository provider, metrics sink,
   clock, and aggregation-job publisher while preserving the existing default constructor.
5. Reworked scheduler unit tests to use fake ports for no-job, successful dispatch, partial publish
   failure, flush timeout, stale reset invocation, dispatch recovery, runtime settings, and bounded
   stop behavior.
6. Added `scripts/aggregation_scheduler_boundary_guard.py` and wired it into
   `make architecture-guard`.
7. Added `docs/standards/aggregation-scheduler-boundary-standard.md` and updated the application
   port catalog.

## Behavior And Compatibility

No Kafka topic, Kafka key, event payload field, correlation header behavior, queue metric name,
stale reset behavior, eligible-claim batch behavior, dispatch recovery error message, database
schema, public API route, consumer contract, poll cadence, or runtime topology changed.

`AggregationScheduler()` remains the runtime construction path used by `ConsumerManager`.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py tests/unit/scripts/test_aggregation_scheduler_boundary_guard.py -q`
2. `python -m pytest tests/unit/services/portfolio_aggregation_service/unit/test_portfolio_aggregation_consumer_manager_runtime.py -q`
3. `python scripts/aggregation_scheduler_boundary_guard.py`
4. `python -m ruff check <touched aggregation scheduler Python paths>`
5. `python -m ruff format --check <touched aggregation scheduler Python paths>`
6. `$env:PYTHONPATH='src/services/portfolio_aggregation_service;src/libs/portfolio-common'; python -c "import app.consumer_manager; import app.core.aggregation_scheduler"`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, application port
catalog, and repo context.

No wiki update is required because this slice changes internal scheduler composition and
testability without changing operator-facing commands, public API behavior, supported features, or
published wiki truth.

No platform skill source change is required in this slice because the existing backend delivery
guidance already covers repeated concrete DB/Kafka coupling patterns through ports, adapters,
fake-port tests, guards, and repo context.

## Remaining Work

GitHub issue #626 is locally fixed for injected settings, clock, repository/session port,
metrics sink, aggregation-job publisher port, pure event/key planning, fake-port unit tests, and
adapter-preserving runtime compatibility pending PR CI/QA and issue closure.

Broader scheduler runtime consolidation and outbox dispatcher publication remain separate issue
scope.
