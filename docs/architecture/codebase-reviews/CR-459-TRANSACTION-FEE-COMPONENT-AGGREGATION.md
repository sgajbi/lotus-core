# CR-459: Transaction Fee Component Aggregation

Date: 2026-05-28

## Scope

Transaction ingestion DTOs, shared `TransactionEvent`, transaction persistence, and downstream
cost-calculator regression coverage for transaction fee handling.

## Finding

Transactions can arrive with a detailed fee breakdown (`brokerage`, `stamp_duty`, `exchange_fee`,
`gst`, and `other_fees`). The persistence repository intentionally excludes those event-only
component fields because the transaction table stores aggregate `trade_fee` and the dedicated cost
breakdown is written later by the cost calculator.

That meant a transaction with component fees and `trade_fee = 0` could be initially persisted with
an understated aggregate fee before cost processing updated it. This is a calculation lineage risk:
raw persisted booking truth, outbox payloads, and interim consumers should not understate the
economic fee total when the component evidence is already present.

## Change

Added a shared transaction-fee helper and applied it at the write boundary:

1. `portfolio_common.transaction_fee_components` now owns the governed component field list and
   aggregate `trade_fee` resolution,
2. ingestion `Transaction` aggregates `trade_fee` from fee components during validation,
3. shared `TransactionEvent` aggregates `trade_fee` from fee components during validation,
4. persistence repository tests prove the persisted transaction carries the aggregate fee even
   though event-only component fields are excluded from the transaction table,
5. cost-calculator consumer regression coverage was updated to expect canonicalized adjustment
   transaction outbox payloads after CR-458.

If no fee components are provided, the existing `trade_fee` value is preserved.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/ingestion_service/test_transaction_model.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py -q`
2. `python -m pytest tests/unit/services/ingestion_service -q`
3. `python -m pytest tests/unit/libs/portfolio_common -q`
4. `python -m pytest tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/integration/services/persistence_service/repositories/test_repositories.py -q`
5. `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
6. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
7. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_fee_components.py src/libs/portfolio-common/portfolio_common/events.py src/services/ingestion_service/app/DTOs/transaction_dto.py tests/unit/services/ingestion_service/test_transaction_model.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
8. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/events.py src/services/ingestion_service/app/DTOs/transaction_dto.py tests/unit/services/ingestion_service/test_transaction_model.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
9. `git diff --check`

Results:

1. Focused ingestion/event/persistence proof: `17 passed`
2. Ingestion-service unit pack: `122 passed`
3. Portfolio-common unit pack: `138 passed`
4. Persistence transaction pack: `17 passed`
5. Cost-calculator consumer pack: `21 passed`
6. Ingestion router integration pack: `212 passed`
7. Touched-surface ruff: passed
8. Touched-surface format check: passed
9. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
booking write boundary now preserves fee economics consistently: detailed component evidence still
flows to the cost engine, and aggregate persisted transaction truth no longer understates fees when
components are provided.
