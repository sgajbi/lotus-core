# CR-1298 Shared Kafka Event Mapping

## Scope

Issue cluster: GitHub issue #662, with supporting coverage for umbrella mapping issue #661.

This slice completes the event-mapping issue locally by covering the remaining named valuation and
pipeline consumers plus pipeline and persistence outbox payload serialization.

## Objective

Reduce design-time complexity and contract drift by centralizing raw Kafka bytes to typed event
validation and typed event to outbox payload serialization in a shared library helper.

## Changes

1. Added `portfolio_common.event_mapping` with deterministic Kafka message identity, JSON payload
   decoding, governed Pydantic event validation, and JSON-safe outbox event payload serialization.
2. Rewired valuation readiness and price-event consumers to consume the shared decode/validation
   helper while preserving existing correlation fallback behavior.
3. Rewired pipeline processed-transaction, cashflow, portfolio-aggregation, and financial
   reconciliation completion consumers to consume the shared decode/validation helper while
   preserving existing correlation precedence.
4. Rewired pipeline outbox payload emission through `outbox_event_payload(...)`.
5. Rewired persistence transaction and market-price outbox payload emission through
   `outbox_event_payload(...)`.
6. Added shared-helper tests for deterministic event identity, invalid JSON rejection,
   validation-error rejection, Decimal/date fidelity, schema/correlation preservation, and outbox
   payload serialization.
7. Added a direct processed-transaction consumer test for stage registration, idempotency metadata,
   header correlation propagation, and invalid-payload DLQ handling.

## Behavior And Compatibility

This is a design-modularity slice inside the existing deployable services. It is not a runtime
service split.

No Kafka topic, event model, event payload shape, outbox table shape, database schema, route path,
idempotency key, stage mutation, valuation job mutation, correlation precedence, DLQ
classification, retry classification, or successful workflow behavior changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/valuation_orchestrator_service/consumers/test_valuation_readiness_consumer.py tests/unit/services/valuation_orchestrator_service/consumers/test_price_event_consumer.py tests/unit/services/pipeline_orchestrator_service/consumers/test_financial_reconciliation_completion_consumer.py tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py -q`
   - 35 passed.
2. `python -m pytest tests/unit/libs/portfolio-common/test_event_mapping.py tests/unit/services/pipeline_orchestrator_service/consumers/test_processed_transaction_stage_consumer.py tests/unit/services/pipeline_orchestrator_service/consumers/test_financial_reconciliation_completion_consumer.py tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py tests/unit/services/valuation_orchestrator_service/consumers/test_valuation_readiness_consumer.py tests/unit/services/valuation_orchestrator_service/consumers/test_price_event_consumer.py tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py tests/unit/services/persistence_service/consumers/test_persistence_market_price_consumer.py -q`
   - 45 passed.
3. `rg -n 'json\.loads|model_validate\(|model_dump\(mode="json"\)' src\services\pipeline_orchestrator_service\app src\services\valuation_orchestrator_service\app\consumers src\services\persistence_service\app -g '*.py'`
   - no remaining inline JSON decode or direct outbox `model_dump(mode="json")` in the targeted pipeline, valuation-consumer, or persistence app paths; the only remaining match is market-price outbox model construction with `MarketPricePersistedEvent.model_validate(...)`.

4. `python -m ruff check src\libs\portfolio-common\portfolio_common\event_mapping.py src\services\persistence_service\app\adapters\persistence_event_adapter.py src\services\valuation_orchestrator_service\app\consumers\valuation_readiness_consumer.py src\services\valuation_orchestrator_service\app\consumers\price_event_consumer.py src\services\pipeline_orchestrator_service\app\consumers\processed_transaction_stage_consumer.py src\services\pipeline_orchestrator_service\app\consumers\cashflow_stage_consumer.py src\services\pipeline_orchestrator_service\app\consumers\portfolio_aggregation_stage_consumer.py src\services\pipeline_orchestrator_service\app\consumers\financial_reconciliation_completion_consumer.py src\services\pipeline_orchestrator_service\app\services\pipeline_orchestrator_service.py src\services\persistence_service\app\consumers\market_price_consumer.py src\services\persistence_service\app\consumers\transaction_consumer.py tests\unit\libs\portfolio-common\test_event_mapping.py tests\unit\services\pipeline_orchestrator_service\consumers\test_processed_transaction_stage_consumer.py`
   - passed.
5. `python -m ruff format --check src\libs\portfolio-common\portfolio_common\event_mapping.py src\services\persistence_service\app\adapters\persistence_event_adapter.py src\services\valuation_orchestrator_service\app\consumers\valuation_readiness_consumer.py src\services\valuation_orchestrator_service\app\consumers\price_event_consumer.py src\services\pipeline_orchestrator_service\app\consumers\processed_transaction_stage_consumer.py src\services\pipeline_orchestrator_service\app\consumers\cashflow_stage_consumer.py src\services\pipeline_orchestrator_service\app\consumers\portfolio_aggregation_stage_consumer.py src\services\pipeline_orchestrator_service\app\consumers\financial_reconciliation_completion_consumer.py src\services\pipeline_orchestrator_service\app\services\pipeline_orchestrator_service.py src\services\persistence_service\app\consumers\market_price_consumer.py src\services\persistence_service\app\consumers\transaction_consumer.py tests\unit\libs\portfolio-common\test_event_mapping.py tests\unit\services\pipeline_orchestrator_service\consumers\test_processed_transaction_stage_consumer.py`
   - passed.
6. `make quality-wiki-docs-gate`
   - passed.
7. `git diff --check`
   - passed with CRLF normalization warnings only.

## Documentation, Wiki, Context, And Skill Decision

Updated the repository mapping/anti-corruption boundary and repo-local engineering context.

No wiki update is required because no operator command, runtime support workflow, API behavior, or
user-facing capability changed.

No central Lotus skill change is required. The durable rule is repository-local and shared-library
backed: new event consumers should use `portfolio_common.event_mapping` for Kafka decode/model
validation and outbox event payload serialization.

## Remaining Work

GitHub issue #662 is locally fixed pending PR CI/QA and issue closure. GitHub issue #661 remains the
umbrella mapping/anti-corruption contract for continued coverage across API DTO command mappers,
additional source-data products, and typed read records.
