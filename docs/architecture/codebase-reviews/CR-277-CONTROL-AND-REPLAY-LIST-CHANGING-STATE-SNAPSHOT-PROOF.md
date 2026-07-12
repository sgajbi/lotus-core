# CR-277 Control And Replay List Changing-State Snapshot Proof

## Summary

The control-stage and replay-key support listings already exposed `generated_at_utc` and repository
`as_of` fences, but we still lacked DB-backed proof that one real list response excludes later
control rows and later replay-key rows that already exist in durable storage around the snapshot.

## Finding

- Class: support list snapshot correctness risk
- Consequence: without an integration proof, these operator drill-through lists still relied on
  repository query shape and service forwarding confidence for their strongest contract: `total` and
  `items` should describe the same durable moment even while more recent rows arrive.

## Action Taken

- extended
  `tests/integration/services/query_service/test_int_operations_service.py`
- fixed the service snapshot time at one durable instant
- added one control-stage list proof that seeds:
  - one older financial-reconciliation control row before the snapshot
  - one later control row after the snapshot
- added one replay-key list proof that seeds:
  - one older replay key before the snapshot
  - one later replay key after the snapshot
- proved that:
  - `get_portfolio_control_stages(...)` returns only the older control row in both `total` and
    `items`
  - `get_reprocessing_keys(...)` returns only the older replay key in both `total` and `items`

## Evidence

- `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`
  - `6 passed`
- `python -m ruff check tests/integration/services/query_service/test_int_operations_service.py`
  - passed

## Follow-up

- keep extending DB-backed snapshot characterization to the remaining support lists, especially
  replay jobs and lineage keys, so operators can trust pagination and row payloads under churn
