# CR-262 Booked Date Snapshot Causality Review

## Summary

The support overview already exposed `generated_at_utc` and fenced most of its “latest” reads to
that snapshot. But the “latest booked” anchors still relied on `*_as_of(date)` helpers that fenced
only by business date, not by the response snapshot timestamp. That allowed a later-ingested row
with an older business date to leak into an otherwise frozen support snapshot.

## Finding

- Class: support-plane correctness risk
- Consequence: `latest_booked_transaction_date` and
  `latest_booked_position_snapshot_date` could reflect durable rows created after the support
  overview’s own `generated_at_utc`, undermining the overview’s snapshot contract.

## Action Taken

- widened:
  - `get_latest_transaction_date_as_of(...)`
  - `get_latest_snapshot_date_for_current_epoch_as_of(...)`
- both helpers now accept optional `snapshot_as_of`
- both queries now fence on:
  - business date scope
  - durable creation time scope
- updated `OperationsService.get_support_overview(...)` to pass:
  - `latest_business_date`
  - `generated_at_utc`
  together into both booked-date lookups
- strengthened repository and service tests to prove the dual fence

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py -q`
  - `103 passed`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py`
  - passed

## Follow-up

- keep checking any helper that sounds like “as of date” but is used inside a timestamped support
  snapshot; business-date fencing alone is not enough when the API also claims a durable response
  timestamp
