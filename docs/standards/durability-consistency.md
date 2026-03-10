# Durability and Consistency Standard (lotus-core)

- Standard reference: `lotus-platform/Durability and Consistency Standard.md`
- Scope: core portfolio data processing, durable ingestion, canonical query outputs.
- Change control: RFC required for policy changes; ADR required for temporary exceptions.

## Workflow Consistency Classification

- Strong consistency:
  - transaction ingestion/booking
  - position/cash updates
  - valuation and cost basis state per `as_of_date`
  - snapshot outputs consumed by proposals/reporting
- Eventual consistency:
  - asynchronous downstream consumption after core durable writes complete

## Idempotency and Replay Protection

- Consumer handlers enforce idempotency checks before processing duplicated events.
- Replay-safe writes use idempotency repository and natural business keys.
- Evidence:
  - `src/libs/portfolio-common/portfolio_common/idempotency_repository.py`
  - `src/services/calculators/position_calculator/app/consumers/transaction_event_consumer.py`
  - `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`
  - `src/services/calculators/position_valuation_calculator/app/consumers/*`

## Atomicity and Transaction Boundaries

- Core state transitions execute within explicit DB transaction boundaries.
- Partial updates are rolled back to prevent ledger/position divergence.
- Evidence:
  - `src/libs/portfolio-common/portfolio_common/unit_of_work.py`
  - service consumer transaction handlers listed above

## As-Of and Reproducibility Semantics

- Canonical API contracts use `as_of_date` for deterministic outputs.
- Epoch-aware query logic preserves atomic snapshot consistency.
- Evidence:
  - `src/services/query_control_plane_service/app/main.py`
  - `src/services/query_service/app/services/integration_service.py`
  - `docs/features/foundational_data_queries/03_Methodology_Guide.md`

## Concurrency and Conflict Policy

- Version/epoch-aware query fences prevent stale state corruption.
- Reprocessing flows handle late arrivals through deterministic epoch model.
- Evidence:
  - `docs/RFCs/RFC 001 - Epoch and Watermark-Based Reprocessing.md`
  - `docs/RFCs/RFC 032 - Query Consistency and Race Condition Hardening.md`

## Integrity Constraints

- Unique/FK/check constraints and schema validation enforce financial invariants.
- Evidence:
  - `src/libs/portfolio-common/portfolio_common/database_models.py`
  - migration scripts under `src/infrastructure/postgres_migrations`

## Release-Gate Tests

- Unit: `tests/unit/services/query_service/*`
- Integration: `tests/integration/services/query_service/*`
- E2E-lite and contract flows covered by CI baseline scripts in PPD automation.

## Deviations

- Deviations from strong consistency for core writes require ADR and expiry review date.


