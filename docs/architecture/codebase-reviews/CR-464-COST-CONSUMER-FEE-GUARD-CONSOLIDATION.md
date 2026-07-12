# CR-464: Cost Consumer Fee Guard Consolidation

Date: 2026-05-28

## Scope

Cost-calculator consumer fee transformation before cost-engine parsing and calculation.

## Finding

The shared transaction event boundary already rejects negative aggregate and component fees, but
the cost-calculator consumer still carried duplicate local fee aggregation logic in
`_transform_event_for_engine(...)`.

That duplication preserved normal behavior for validated events, but it made the consumer weaker
than the shared fee policy if an event was mutated after validation. A post-validation negative
`trade_fee` could be converted to zero, and a negative fee component could bypass the shared
fail-closed message until local decimal conversion.

## Change

Reused `portfolio_common.transaction_fee_components.resolve_transaction_trade_fee(...)` inside the
cost consumer transformation path. The consumer now uses the same aggregate/component fee guard as
ingestion and shared `TransactionEvent` validation.

Added tests proving post-validation negative aggregate and component fees fail closed in
`_transform_event_for_engine(...)` before the event reaches cost-engine parsing.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
4. `python -m ruff check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
5. `python -m ruff format --check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
6. `git diff --check`

Results:

1. Focused cost-consumer proof: `25 passed`
2. Cost-calculator unit pack: `104 passed`
3. Portfolio-common unit pack: `482 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Cost
fee transformation now follows the same shared fee economics guard as the event boundary.
