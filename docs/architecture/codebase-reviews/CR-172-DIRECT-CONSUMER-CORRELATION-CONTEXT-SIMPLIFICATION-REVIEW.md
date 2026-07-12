# CR-172 Direct Consumer Correlation Context Simplification Review

## Finding
Several direct-invocation consumers had already been migrated onto the shared
`_message_correlation_context(...)` helper, but they still re-read
`correlation_id_var` inside the context body. That left the code depending on
ambient context even after entering the explicit message-scoped contract.

## Change
Switched the reviewed consumers to use the correlation id yielded by
`_message_correlation_context(...)` directly and removed the no-longer-needed
`correlation_id_var` imports.

## Outcome
The consumer code is now simpler and more explicit:
- one correlation contract instead of two
- less ambient state coupling
- easier future review of direct-path lineage handling

## Evidence
- `src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py`
- `src/services/persistence_service/app/consumers/base_consumer.py`
- `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`
- `src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py`
- `src/services/calculators/cost_calculator_service/app/consumer.py`
- `src/services/calculators/position_calculator/app/consumers/transaction_event_consumer.py`
