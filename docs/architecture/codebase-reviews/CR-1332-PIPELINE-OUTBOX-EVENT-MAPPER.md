# CR-1332 Pipeline Outbox Event Mapper

## Objective

Complete the remaining representative slice for GitHub issue #662 by moving pipeline outbox event
payload serialization behind an explicit adapter.

## Expected Improvement

Pipeline orchestration methods still own stage decisions, aggregate IDs, topics, and event types,
but no longer call shared event serialization directly. The outbox payload boundary is now isolated
and tested for governed event metadata and Decimal/date fidelity while existing event-runtime
catalog discovery still sees explicit outbox emissions.

## Changes

1. Added `pipeline_orchestrator_service/app/adapters/outbox_event_mapper.py`.
2. Routed pipeline outbox payload construction through `pipeline_outbox_event_payload(...)`.
3. Added mapper tests proving `event_type`, `schema_version`, `correlation_id`, datetime, and
   Decimal serialization.
4. Wired the touched pipeline adapter/service/tests into the scoped lint target.

## Compatibility Impact

No Kafka topic, event type, schema version, payload field, aggregate ID, database schema, route,
OpenAPI contract, runtime topology, or operator behavior changed.

## No Runtime Split Decision

This is an in-process event adapter boundary. It does not create a new service, queue, database,
worker, scheduler, or deployment boundary.

## Validation Evidence

Focused validation was run before commit:

1. `python -m pytest tests/unit/libs/portfolio-common/test_event_mapping.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/unit/services/pipeline_orchestrator_service/adapters/test_outbox_event_mapper.py tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py -q`
2. `python scripts/event_runtime_contract_guard.py`
3. Scoped Ruff check over changed pipeline adapter/service/test files.
4. Scoped Ruff format check over changed pipeline adapter/service/test files.
5. `python scripts/wiki_validation_guard.py`
6. `git diff --check`
