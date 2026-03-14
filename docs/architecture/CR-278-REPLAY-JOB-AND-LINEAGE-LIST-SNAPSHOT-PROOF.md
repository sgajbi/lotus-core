# CR-278 Replay Job And Lineage List Snapshot Proof

## Summary

The replay-job and lineage-key support listings already exposed `generated_at_utc` and repository
`as_of` fences, but we still lacked DB-backed proof that one real list response excludes later
replay jobs and later lineage keys under durable churn around the snapshot moment.

## Finding

- Class: support list snapshot correctness risk
- Consequence: without an integration proof, these lists still relied on repository query shape and
  service forwarding confidence for their strongest contract: `total`, returned rows, and projected
  derived fields should all describe the same durable moment while later state already exists.

## Action Taken

- extended
  `tests/integration/services/query_service/test_int_operations_service.py`
- fixed the service snapshot time at one durable instant
- added one replay-job list proof that seeds:
  - one older replay job with valid portfolio scope before the snapshot
  - one later replay job after the snapshot
- added one lineage-key list proof that seeds:
  - one older lineage key with projected history, snapshot, and valuation artifacts before the
    snapshot
  - one later lineage key and later projected artifacts after the snapshot
- proved that:
  - `get_reprocessing_jobs(...)` returns only the older replay job in both `total` and `items`
  - `get_lineage_keys(...)` returns only the older lineage key in both `total` and `items`
  - the projected lineage artifacts also stay aligned to the same older snapshot

## Evidence

- `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`
  - `8 passed`
- `python -m ruff check tests/integration/services/query_service/test_int_operations_service.py`
  - passed

## Follow-up

- keep using DB-backed churn proofs to close the remaining support-plane trust gaps before we call
  this area gold-standard
