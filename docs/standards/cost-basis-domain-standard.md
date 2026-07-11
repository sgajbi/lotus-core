# Cost-Basis Domain Standard

Cost-basis domain models represent calculation-owned transaction state. They must remain
framework-independent so cost processing can run without API, event, or persistence libraries.

## Rules

1. `portfolio_transaction_processing_service/app/domain/cost_basis` modules must not import
   Pydantic, FastAPI, SQLAlchemy, Kafka clients, HTTP clients, repositories, database sessions, or
   service settings.
2. API/event validation belongs at adapter boundaries before data enters the domain.
3. Parser construction may coerce raw adapter dictionaries into domain objects, but calculation
   modules should consume pure Python domain objects.
4. Domain objects may expose compatibility helpers such as `model_dump(...)` or `model_copy(...)`
   only when required to preserve existing internal workflow/repository contracts during migration.
5. New cost-basis calculation behavior should use explicit domain fields, policies, or shared
   value objects instead of adding transport-specific model metadata.

## Current Guard

`tests/unit/services/portfolio_transaction_processing_service/test_cost_basis_domain_structure.py`
checks package naming, module docstrings, and legacy-path retirement. The generic testability
architecture guard enforces framework and infrastructure independence for the complete target
domain package.
