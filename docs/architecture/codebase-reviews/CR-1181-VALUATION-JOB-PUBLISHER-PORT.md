# CR-1181 Valuation Job Publisher Port

## Objective

Begin GitHub issue #653 by moving a representative scheduler publishing path from direct Kafka
producer usage to an explicit event publisher port.

## Expected Improvement

- `ValuationScheduler` no longer imports `KafkaProducer` or `get_kafka_producer`.
- Valuation job dispatch depends on a `ValuationJobPublisher` protocol with explicit publish and
  delivery-confirmation semantics.
- Kafka-specific topic wiring and flush calls are isolated in `KafkaValuationJobPublisher`.
- `make architecture-guard` blocks reintroducing concrete Kafka utility imports in
  `valuation_scheduler.py`.

## Changes

- Added `src/services/valuation_orchestrator_service/app/core/valuation_job_publisher.py`.
- Added `ValuationJobPublisher` and `KafkaValuationJobPublisher`.
- Added constructor injection for `ValuationScheduler(..., valuation_job_publisher=...)`.
- Routed valuation job publish and flush confirmation through the publisher port.
- Updated scheduler tests to inject the Kafka adapter around a mock producer.
- Updated valuation dispatch assertions to include the current governed event envelope fields.
- Extended architecture boundary guard coverage for the valuation scheduler.

## Compatibility

No Kafka topic, Kafka key, Kafka headers, event payload construction, dispatch ordering, partial
failure handling, flush timeout behavior, scheduler polling behavior, database schema, API route,
or downstream consumer contract changed. The scheduler now obtains the same Kafka-backed behavior
through an injected port instead of constructing a concrete producer itself.

## Validation

- `python -m pytest tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/scripts/test_architecture_boundary_guard.py -q`
- `make architecture-guard`
- `make quality-import-boundary-gate`
- `python -m ruff check src/services/valuation_orchestrator_service/app/core/valuation_job_publisher.py src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py scripts/architecture_boundary_guard.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/scripts/test_architecture_boundary_guard.py`
- `python -m ruff format --check src/services/valuation_orchestrator_service/app/core/valuation_job_publisher.py src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py scripts/architecture_boundary_guard.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/scripts/test_architecture_boundary_guard.py`
- `git diff --check`

## Documentation And Wiki Decision

Updated the codebase review ledger, this CR evidence note, and quality scorecard/health report
because an enforceable publisher-port architecture boundary changed. No wiki source update is
required because no operator workflow or public API contract changed.

## Follow-Up

Issue #653 remains open. Future slices should add publisher ports for ingestion, outbox dispatch,
aggregation scheduler dispatch, and reprocessing replay paths, then restrict concrete Kafka
producer usage to infrastructure adapter modules.
