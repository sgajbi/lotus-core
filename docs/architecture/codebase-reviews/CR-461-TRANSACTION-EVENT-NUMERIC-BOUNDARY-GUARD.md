# CR-461: Transaction Event Numeric Boundary Guard

Date: 2026-05-28

## Scope

Shared `TransactionEvent` validation and cost-calculator consumer handling for malformed
transaction amount, FX amount, and rate fields.

## Finding

The ingestion DTO already constrains many transaction amount fields, but shared `TransactionEvent`
could still be constructed directly with negative core values such as `quantity`, `price`, or
`gross_transaction_amount`. It could also accept non-positive FX amounts or rates such as
`buy_amount`, `sell_amount`, `contract_rate`, `transaction_fx_rate`, and synthetic-flow FX rates.

Those values violate cost-engine and transaction-domain assumptions. Letting them reach
calculation code risks misleading derived costs, cashflows, FX contract state, and downstream
supportability evidence.

## Change

Added raw event-boundary numeric guards:

1. `TransactionEvent` rejects negative `quantity`, `price`, `gross_transaction_amount`,
   `synthetic_flow_price_used`, and `synthetic_flow_quantity_used`,
2. `TransactionEvent` rejects non-positive `transaction_fx_rate`, `buy_amount`, `sell_amount`,
   `contract_rate`, and `synthetic_flow_fx_rate_to_base` when supplied,
3. cost-calculator consumer coverage proves a negative gross transaction amount is sent to DLQ
   before history lookup, cost calculation, or persistence update work begins.

Signed fields that are legitimately directional, such as synthetic-flow local/base amounts,
`net_cost`, realized P&L, and cashflow-derived effects, were intentionally left out of this guard.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
4. `python -m pytest tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/integration/services/persistence_service/repositories/test_repositories.py -q`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
7. `git diff --check`

Results:

1. Focused event/cost proof: `29 passed`
2. Portfolio-common unit pack: `142 passed`
3. Cost-calculator consumer pack: `23 passed`
4. Persistence transaction pack: `17 passed`
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The raw
transaction event boundary now fails closed for amount and rate values that downstream calculators
cannot safely interpret.
