# CR-106: Portfolio Aggregation Consumer Ownership Review

Date: 2026-03-12
Status: Hardened

## Problem

`PortfolioTimeseriesConsumer` still existed in both:

- `portfolio_aggregation_service`
- `timeseries_generator_service`

But only `portfolio_aggregation_service` actually owns and wires this consumer at runtime.

That left a dead duplicate implementation in `timeseries_generator_service`, plus unit tests still pointing at the wrong owner.

## Why it mattered

This was not harmless duplication.

- ownership was blurred
- future fixes could land in the dead copy
- direct-path correlation hardening could be applied to the wrong service

For a scheduler/aggregation path, duplicated runtime consumers are unacceptable residue.

## Fix

- Deleted the dead duplicate:
  - `src/services/timeseries_generator_service/app/consumers/portfolio_timeseries_consumer.py`
- Moved the unit tests under the live owner:
  - `tests/unit/services/portfolio_aggregation_service/consumers/test_portfolio_timeseries_consumer.py`
- Updated the live owner consumer to use `_message_correlation_context(...)` so direct invocation preserves the Kafka header correlation id.
- Applied the same direct-path correlation hardening to `PositionTimeseriesConsumer` in `timeseries_generator_service`.
- Corrected stale file-header comments after the move.

## Proof

Validated:

- `tests/unit/services/portfolio_aggregation_service/consumers/test_portfolio_timeseries_consumer.py`
- `tests/unit/services/timeseries_generator_service/timeseries-generator-service/consumers/test_position_timeseries_consumer.py`

Result:

- `8 passed`

## Follow-up

Keep aggregation-consumer ownership singular:

- `portfolio_aggregation_service` owns portfolio aggregation
- `timeseries_generator_service` owns position-timeseries generation only
