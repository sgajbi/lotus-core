# CR-276 Reconciliation List Changing-State Snapshot Proof

## Summary

Reconciliation support listings already carried `generated_at_utc` and repository `as_of` fences,
but we still lacked DB-backed proof that one real run-list response excludes later runs and one
real finding-list response excludes later findings under active control churn.

## Finding

- Class: support list snapshot correctness risk
- Consequence: without an integration proof, reconciliation support listings still relied on query
  shape and unit forwarding confidence for their strongest contract: count, ordering, and returned
  rows should all describe one durable snapshot even while more severe rows are arriving.

## Action Taken

- extended
  `tests/integration/services/query_service/test_int_operations_service.py`
- fixed the service snapshot time at one durable instant
- added one run-list proof that seeds:
  - one older reconciliation run before the snapshot
  - one later failed reconciliation run after the snapshot
- added one finding-list proof that seeds:
  - one older blocking finding before the snapshot
  - one later blocking finding after the snapshot
- proved that:
  - `get_reconciliation_runs(...)` returns only the older run in both `total` and `items`
  - `get_reconciliation_findings(...)` returns only the older finding in both `total` and `items`

## Evidence

- `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`
  - `4 passed`
- `python -m ruff check tests/integration/services/query_service/test_int_operations_service.py`
  - passed

## Follow-up

- keep applying DB-backed snapshot characterization to the remaining operator drill-through lists so
  count, ordering, and row payloads are all proven under real durable churn
