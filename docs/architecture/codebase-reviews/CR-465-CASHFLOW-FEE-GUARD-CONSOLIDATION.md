# CR-465: Cashflow Fee Guard Consolidation

Date: 2026-05-28

## Scope

Cashflow calculator fee handling for transaction-derived cashflows.

## Finding

Cashflow calculation read `transaction.trade_fee` directly even though ingestion, shared
`TransactionEvent`, and the cost consumer now use the shared aggregate/component fee guard.

Validated Kafka events were already protected, but direct calculator calls and post-validation
mutation could still let negative aggregate or component fee values distort cashflow amounts before
the Prometheus counter and `Cashflow` row were created.

## Change

Added a cashflow-local fee resolver that delegates to
`portfolio_common.transaction_fee_components.resolve_transaction_trade_fee(...)`. `CashflowLogic`
now uses that resolved fee for BUY, SELL, FEE, DIVIDEND, INTEREST, and other transaction cashflow
amounts.

Added direct calculator tests proving post-validation negative aggregate and component fees fail
closed before metric emission or cashflow creation.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py -q`
2. `python -m pytest tests/unit/services/calculators/cashflow_calculator_service -q`
3. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
4. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
5. `python -m ruff check src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
6. `python -m ruff format --check src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
7. `git diff --check`

Results:

1. Focused cashflow-logic proof: `35 passed`
2. Cashflow-calculator unit pack: `60 passed`
3. Portfolio-common unit pack: `482 passed`
4. Cost-calculator unit pack: `104 passed`
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Cashflow
amount calculation now follows the same shared fee economics guard as ingestion, shared events, and
cost processing.
