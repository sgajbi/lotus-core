# CR-272 Aggregation Consumer Ownership-Loss Proof

## Summary

The aggregation consumer already gated completion side effects behind durable terminal ownership, but
we still lacked DB-backed proof that a late ownership loss would suppress durable portfolio
timeseries and outbox writes.

## Finding

- Class: concurrency correctness risk
- Consequence: without an integration proof, the aggregation consumer still relied on unit-level
  confidence for the guarantee that a late worker does not publish completion side effects after job
  ownership has already been lost.

## Action Taken

- added an integration proof in
  `tests/integration/services/portfolio_aggregation_service/test_int_portfolio_timeseries_consumer_persistence.py`
- used a second database session to mark the same aggregation job `COMPLETE` immediately before the
  real `_update_job_status(...)` executes
- patched the logic layer only to supply a deterministic portfolio-timeseries record while keeping
  the real consumer path and real status update semantics
- proved that the consumer then:
  - writes no `PortfolioTimeseries`
  - emits no aggregation completion outbox event
  - leaves the durable job row completed by the competing owner

## Evidence

- `python -m pytest tests/integration/services/portfolio_aggregation_service/test_int_portfolio_timeseries_consumer_persistence.py -q`
  - `1 passed`
- `python -m ruff check tests/integration/services/portfolio_aggregation_service/test_int_portfolio_timeseries_consumer_persistence.py`
  - passed

## Follow-up

- keep looking for any remaining worker consumer that can still emit durable completion side effects
  after status ownership is lost
