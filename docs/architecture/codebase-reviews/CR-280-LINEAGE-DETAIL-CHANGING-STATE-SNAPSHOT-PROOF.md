# CR-280 Lineage Detail Changing-State Snapshot Proof

## Summary

The lineage detail endpoint already exposed `generated_at_utc` and repository `as_of` fences, but
we still lacked DB-backed proof that one real response excludes later history, snapshot, and
valuation artifacts when durable lineage data keeps changing around the snapshot moment.

## Finding

- Class: support detail snapshot correctness risk
- Consequence: without an integration proof, lineage detail still relied on repository query shape
  and service forwarding confidence for its strongest contract: the current lineage row, projected
  artifact dates, and derived health should all describe the same durable moment while later
  artifacts already exist.

## Action Taken

- extended `tests/integration/services/query_service/test_int_operations_service.py`
- fixed the service snapshot time at one durable instant
- added one lineage-detail proof that seeds:
  - one current lineage row with valid history, snapshot, and valuation artifacts before the
    snapshot
  - later history, snapshot, and valuation artifacts after the snapshot for the same lineage row
- proved that `get_lineage(...)` returns only the older snapshot-visible artifacts, with derived
  `has_artifact_gap` and `operational_state` aligned to that same snapshot

## Evidence

- `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`
  - `12 passed`
- `python -m ruff check tests/integration/services/query_service/test_int_operations_service.py`
  - passed

## Follow-up

- keep extending DB-backed churn proofs to the remaining detail surfaces where projected fields and
  derived operator state still need live-response evidence under changing durable state
