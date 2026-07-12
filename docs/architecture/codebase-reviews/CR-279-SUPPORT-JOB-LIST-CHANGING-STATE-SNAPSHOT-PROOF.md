# CR-279 Support Job List Changing-State Snapshot Proof

## Summary

The valuation, aggregation, and analytics-export support listings already exposed
`generated_at_utc` and repository `as_of` fences, but we still lacked DB-backed proof that one
real list response excludes later jobs under durable churn around the snapshot moment.

## Finding

- Class: support list snapshot correctness risk
- Consequence: without an integration proof, these three core operator lists still relied on query
  shape and service forwarding confidence for their strongest contract: `total`, returned rows,
  and derived stale-state classification should all describe the same durable moment while later
  queue state already exists.

## Action Taken

- extended `tests/integration/services/query_service/test_int_operations_service.py`
- fixed the service snapshot time at one durable instant
- added one valuation-job list proof that seeds:
  - one older visible valuation job before the snapshot
  - one later valuation job after the snapshot
- added one aggregation-job list proof that seeds:
  - one older visible aggregation job before the snapshot
  - one later aggregation job after the snapshot
- added one analytics-export list proof that seeds:
  - one older visible running export job before the snapshot
  - one later export job after the snapshot
- proved that:
  - `get_valuation_jobs(...)` returns only the older valuation job in both `total` and `items`
  - `get_aggregation_jobs(...)` returns only the older aggregation job in both `total` and `items`
  - `get_analytics_export_jobs(...)` returns only the older export job in both `total` and `items`
  - stale-state classification stays aligned to that same older snapshot

## Evidence

- `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`
  - `11 passed`
- `python -m ruff check tests/integration/services/query_service/test_int_operations_service.py`
  - passed

## Follow-up

- keep extending DB-backed churn proofs to any remaining support/detail surface where count, rows,
  and derived operator state still need live-response evidence under changing storage state
