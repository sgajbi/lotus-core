# CR-275 Calculator SLO Changing-State Snapshot Proof

## Summary

`calculator-slos` already forwarded a shared `generated_at_utc` through repository summary methods, but
we still lacked DB-backed proof that one real response excludes later business dates, later replay
state, and later valuation/aggregation jobs that already exist in durable storage around the
snapshot moment.

## Finding

- Class: support snapshot correctness risk
- Consequence: without an integration proof, the SLO summary still relied on unit-level forwarding
  confidence for its strongest contract: one response should use one durable business-date and queue
  snapshot even while adjacent queue state keeps moving.

## Action Taken

- added an integration proof in
  `tests/integration/services/query_service/test_int_operations_service.py`
- fixed the service snapshot time at one durable instant
- seeded:
  - a later business date created after the response snapshot
  - a later replay key updated after the response snapshot
  - a later valuation job updated after the response snapshot
  - a later aggregation job updated after the response snapshot
- proved that one real `get_calculator_slos(...)` response still returns:
  - the older business date
  - only the older replay key state
  - only the older valuation backlog/failure totals
  - only the older aggregation backlog/failure totals

## Evidence

- `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`
  - `2 passed`
- `python -m ruff check tests/integration/services/query_service/test_int_operations_service.py`
  - passed

## Follow-up

- keep adding DB-backed characterization for summary endpoints that operators use for first-pass
  triage, especially where later queue churn could otherwise blur business-date or backlog truth
