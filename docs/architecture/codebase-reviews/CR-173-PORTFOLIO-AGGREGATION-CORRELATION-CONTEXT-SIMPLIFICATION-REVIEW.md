# CR-173 Portfolio Aggregation Correlation Context Simplification Review

## Finding
`PortfolioTimeseriesConsumer` already used the shared
`_message_correlation_context(...)` helper, but still re-read
`correlation_id_var` inside the context body. That left one more active
aggregation-path consumer depending on ambient state after entering the explicit
message-scoped contract.

## Change
Switched the consumer to use the correlation id yielded by
`_message_correlation_context(...)` directly and removed the redundant
`correlation_id_var` import.

## Outcome
The aggregation path now follows the same explicit correlation contract as the
other reviewed direct consumers. That reduces ambient-state coupling and keeps
message lineage easier to reason about in one of the banking-critical fan-out
paths.

## Evidence
- `src/services/portfolio_aggregation_service/app/consumers/portfolio_timeseries_consumer.py`
- `tests/unit/services/portfolio_aggregation_service/consumers/test_portfolio_timeseries_consumer.py`
