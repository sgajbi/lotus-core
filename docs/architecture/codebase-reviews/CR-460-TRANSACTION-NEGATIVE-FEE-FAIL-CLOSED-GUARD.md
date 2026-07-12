# CR-460: Transaction Negative-Fee Fail-Closed Guard

Date: 2026-05-28

## Scope

Shared transaction fee resolution, ingestion DTO validation, shared `TransactionEvent`, and
cost-calculator consumer handling for malformed transaction fee economics.

## Finding

CR-459 ensured detailed fee components aggregate into `trade_fee`, but the shared event boundary
still allowed negative aggregate or component fee values when events were constructed outside the
ingestion DTO. In the cost-calculator consumer, a negative aggregate `trade_fee` without component
details could be transformed into zero because only positive `trade_fee` values were mapped into
the engine fee model.

That is a banking calculation correctness risk: negative fee values should not silently reduce or
erase economic fee evidence. They should fail closed at the event boundary and move to the governed
invalid-payload path.

## Change

Hardened shared fee resolution:

1. `resolve_transaction_trade_fee(...)` rejects negative aggregate `trade_fee`,
2. `resolve_transaction_trade_fee(...)` rejects negative `brokerage`, `stamp_duty`,
   `exchange_fee`, `gst`, and `other_fees` components,
3. shared `TransactionEvent` now raises validation errors for negative fee economics,
4. ingestion `Transaction` retains the same fail-closed posture through the shared helper and
   existing constrained DTO fields,
5. cost-calculator consumer coverage proves negative `trade_fee` is sent to DLQ before history,
   cost calculation, or persistence update work begins.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/ingestion_service/test_transaction_model.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
2. `python -m pytest tests/unit/services/ingestion_service -q`
3. `python -m pytest tests/unit/libs/portfolio_common -q`
4. `python -m pytest tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/integration/services/persistence_service/repositories/test_repositories.py -q`
5. `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
6. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
7. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_fee_components.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/ingestion_service/test_transaction_model.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
8. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/transaction_fee_components.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/ingestion_service/test_transaction_model.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
9. `git diff --check`

Results:

1. Focused fee guard proof: `40 passed`
2. Ingestion-service unit pack: `123 passed`
3. Portfolio-common unit pack: `140 passed`
4. Persistence transaction pack: `17 passed`
5. Cost-calculator consumer pack: `22 passed`
6. Ingestion router integration pack: `212 passed`
7. Touched-surface ruff: passed
8. Touched-surface format check: passed
9. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Fee
economics now fail closed at the shared event boundary instead of being silently converted to zero
in downstream cost processing.
