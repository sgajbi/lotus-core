# CR-263 Current Epoch Snapshot Date Join Fence Review

## Summary

The snapshot-date helpers in `OperationsRepository` fenced `DailyPositionSnapshot.created_at`, but
they did not fence the `PositionState` side of the join that defines “current epoch.” That left a
subtle drift path: a later epoch bump could change which `PositionState` row counted as current
even when the response timestamp and snapshot row itself were already fenced.

## Finding

- Class: support-plane correctness risk
- Consequence: support-overview snapshot date anchors could still reflect a newer epoch selection
  than the one that existed at the claimed support snapshot moment.

## Action Taken

- tightened:
  - `get_latest_snapshot_date_for_current_epoch(...)`
  - `get_latest_snapshot_date_for_current_epoch_as_of(...)`
- both queries now fence:
  - `DailyPositionSnapshot.created_at`
  - `PositionState.updated_at`
  to the same snapshot timestamp
- strengthened repository SQL tests to prove the join-side fence is present

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
  - `60 passed`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
  - passed

## Follow-up

- keep checking any query that derives “current” state through a join; fencing only the fact table
  is not enough if the state table itself can move after the response snapshot
