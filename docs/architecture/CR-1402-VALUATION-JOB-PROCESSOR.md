# CR-1402 Valuation Job Processor

## Objective

Fix GitHub issue #535 by moving valuation job workflow, state vocabulary, snapshot valuation
decisions, repository/idempotency/outbox wiring, and job state transitions out of the Kafka consumer
into an application processor.

## Expected Improvement

- `ValuationConsumer` now owns transport work only: Kafka payload decoding, correlation context,
  retry classification, DLQ handoff, and start logging.
- `ValuationJobProcessor` owns valid-event application workflow, including idempotency claim,
  position-state lookup, reference-data lookup, missing reference handling, valuation snapshot
  construction, missing-price handling, stale/current classification, missing-FX failure handling,
  valuation job completion, no-position skip, unexpected-error failure marking, and outbox staging.
- `ValuationProcessorDependencyFactory` isolates concrete `ValuationRepository`,
  `IdempotencyRepository`, and `OutboxRepository` construction at the runtime wiring boundary.
- The valuation workflow is executable in tests without constructing a Kafka consumer object.
- Backfill/replay entry points can reuse the processor by injecting a session provider and
  dependency factory instead of copying consumer logic.
- The change improves design modularity inside the existing deployable; no runtime service split is
  justified.

## Scope

- Added `valuation_processor.py` with `ValuationJobProcessor`,
  `ValuationProcessorDependencies`, `ValuationProcessorDependencyFactory`, valuation status
  vocabulary, reference-data/result value objects, and retryable data-not-found handling.
- Reduced `consumers/valuation_consumer.py` from workflow owner to transport delegate.
- Updated unit and DB-backed integration tests to patch the processor boundary.
- Added direct processor tests for success without Kafka, duplicate idempotency skip, missing price,
  and stale price.

## Behavior And Compatibility

No Kafka topic, event payload, outbox event type, idempotency service name, valuation result,
job-status value, database schema, OpenAPI contract, or runtime topology changed. Existing
successful valuation, no-position skip, lost-ownership skip, same-scope redelivery refresh,
missing-FX failure, and DLQ behavior are preserved.

## Same-Pattern Scan

- `rg "VALUATION_FAILED|VALUATION_UNVALUED|VALUATION_VALUED|VALUATION_JOB_|ValuationLogic|ValuationRepository\\(|IdempotencyRepository\\(|OutboxRepository\\(|get_async_db_session" src/services/calculators/position_valuation_calculator/app/consumers src/services/calculators/position_valuation_calculator/app/valuation_processor.py tests/unit/services/calculators/position_valuation_calculator/consumers tests/integration/services/calculators/position_valuation_calculator`
  shows valuation state vocabulary and concrete construction live in `valuation_processor.py`, not
  the consumer. Remaining `ValuationRepository(...)` hits are repository-specific integration tests.

## Validation Evidence

- `python -m pytest tests\unit\services\calculators\position_valuation_calculator\consumers\test_valuation_consumer.py -q`
  - `11 passed`
- `python -m pytest tests\integration\services\calculators\position_valuation_calculator\test_int_valuation_consumer_persistence.py -q`
  - `3 passed`
- Scoped Ruff lint and format checks passed for the processor, consumer, and focused tests.

Final architecture/docs/lint/type/diff checks are recorded in the issue comment before commit.

## Documentation And Guidance Decision

- Repo context updated because future Kafka consumers should delegate valid-message application
  workflow and state-transition vocabulary to processors/use cases with explicit dependency
  factories.
- Codebase review ledger updated with this hardened boundary.
- No wiki update: no operator command, endpoint contract, deployment flow, or runbook truth changed.
- No platform skill update: #535 is covered by the newly reinforced backend delivery and codebase
  review guidance around concrete external-capability coupling and processor/dependency-factory
  boundaries.
