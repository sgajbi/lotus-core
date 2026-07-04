# Cost Engine Domain Model Standard

Cost-engine domain models represent calculation-owned transaction state. They must remain
framework-independent so cost processing can run without API, event, or persistence libraries.

## Rules

1. `cost_engine/domain` modules must not import Pydantic, FastAPI, SQLAlchemy, Kafka clients, HTTP
   clients, repositories, database sessions, or service settings.
2. API/event validation belongs at adapter boundaries before data enters the engine.
3. Parser construction may coerce raw adapter dictionaries into domain objects, but calculation
   modules should consume pure Python domain objects.
4. Domain objects may expose compatibility helpers such as `model_dump(...)` or `model_copy(...)`
   only when required to preserve existing internal engine/repository contracts during migration.
5. New cost-engine calculation behavior should use explicit domain fields, policies, or shared
   value objects instead of adding transport-specific model metadata.

## Current Guard

`tests/unit/services/calculators/cost_calculator_service/engine/test_transaction_model.py` checks
that `cost_engine/domain` does not import Pydantic.
