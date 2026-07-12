# CR-1297 Persistence Event Mapping Adapters

## Scope

Issue cluster: GitHub issue #662, with supporting coverage for umbrella mapping issue #661.

This slice covers the persistence-service event boundary. The remaining #662 scope was completed
locally by CR-1298, which adds shared Kafka event mapping and rewires valuation/pipeline consumers
plus outbox payload serialization.

## Objective

Reduce design-time complexity in persistence consumers and repositories by moving Kafka message
decode/validation metadata and event-to-record business value extraction behind explicit adapters.

## Changes

1. Added `persistence_event_adapter.py` for deterministic Kafka event identity, decoded payload
   fallback correlation, Pydantic event validation, idempotency-key derivation, and portfolio-scope
   derivation.
2. Added `event_record_mapper.py` for validated event-to-record business values and transaction
   event-to-transaction-table mapping.
3. Rewired `GenericPersistenceConsumer` to consume decoded/validated adapter envelopes while
   preserving the existing correlation context, idempotency repository call, outbox creation, DLQ
   path, and retry behavior.
4. Rewired portfolio, instrument, market-price, FX-rate, and transaction repositories to consume
   adapter-owned event record values instead of calling `event_business_payload(...)` directly.
5. Extended boundary mapping conformance tests with direct persistence message adapter coverage for
   event identity, correlation lineage, transaction idempotency, portfolio scope, and non-transaction
   event fallback behavior.

## Behavior And Compatibility

This is a design-modularity slice inside the existing persistence service deployable. It is not a
runtime service split.

No route path, Kafka topic, event model, event payload shape, outbox table shape, database schema,
repository SQL conflict key, idempotency key for transaction events, correlation precedence, DLQ
classification, retry classification, or successful persistence behavior changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py -q`
   - 18 passed.
2. `python -m pytest tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/unit/services/persistence_service/repositories/test_persistence_portfolio_repository.py tests/unit/services/persistence_service/repositories/test_persistence_instrument_repository.py tests/unit/services/persistence_service/repositories/test_persistence_fx_rate_repository.py tests/unit/services/persistence_service/repositories/test_market_price_repository.py tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py tests/unit/services/persistence_service/consumers/test_persistence_instrument_consumer.py tests/unit/services/persistence_service/consumers/test_persistence_fx_rate_consumer.py tests/unit/services/persistence_service/consumers/test_persistence_market_price_consumer.py -q`
   - 29 passed.
3. `python scripts/test_manifest.py --suite boundary-mapping-conformance --quiet`
   - 6 passed.

4. `python -m ruff check src\services\persistence_service\app\adapters src\services\persistence_service\app\consumers\base_consumer.py src\services\persistence_service\app\repositories\instrument_repository.py src\services\persistence_service\app\repositories\market_price_repository.py src\services\persistence_service\app\repositories\fx_rate_repository.py src\services\persistence_service\app\repositories\portfolio_repository.py src\services\persistence_service\app\repositories\transaction_db_repo.py tests\unit\boundary_mapping\test_transaction_and_source_data_conformance.py tests\unit\services\persistence_service\repositories\test_transaction_db_repository.py`
   - passed.
5. `python -m ruff format --check src\services\persistence_service\app\adapters src\services\persistence_service\app\consumers\base_consumer.py src\services\persistence_service\app\repositories\instrument_repository.py src\services\persistence_service\app\repositories\market_price_repository.py src\services\persistence_service\app\repositories\fx_rate_repository.py src\services\persistence_service\app\repositories\portfolio_repository.py src\services\persistence_service\app\repositories\transaction_db_repo.py tests\unit\boundary_mapping\test_transaction_and_source_data_conformance.py tests\unit\services\persistence_service\repositories\test_transaction_db_repository.py`
   - passed.
6. `make quality-wiki-docs-gate`
   - passed.
7. `git diff --check`
   - passed with CRLF normalization warnings only.

## Documentation, Wiki, Context, And Skill Decision

Updated the repository mapping/anti-corruption boundary and repo-local engineering context.

No wiki update is required because no operator command, runtime support workflow, API behavior, or
user-facing capability changed.

No central Lotus skill change is required. The repeatable rule is repository-local: persistence
services should keep event decode/validation metadata and event-to-record business mapping in
adapters, while repositories own table-specific SQL conflict and query behavior.

## Remaining Work

CR-1298 completes the remaining #662 valuation, pipeline consumer, and outbox mapping scope
locally. Keep #661 open until representative API DTO, event, persistence, and source-data mapper
families are covered by conformance evidence.
