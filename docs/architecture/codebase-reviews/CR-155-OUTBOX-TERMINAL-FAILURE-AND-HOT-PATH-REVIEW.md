# CR-155 - Outbox Terminal Failure And Hot-Path Review

## Summary

`OutboxDispatcher` had a real queue-correctness gap: `MAX_RETRIES` existed but was not enforced. Permanently failing outbox rows stayed `PENDING` forever, continued to be selected by the dispatcher, and kept applying avoidable pressure to the delivery path. The table also lacked the composite indexes that match the dispatcher's actual selection pattern.

## Findings

1. `outbox_events` selection is driven by `status='PENDING' ORDER BY created_at`.
2. The dispatcher only incremented `retry_count`; it never transitioned irrecoverable rows to a terminal state.
3. That meant repeated poison rows remained in the live queue indefinitely.

## Fix

1. Enforce terminal failure semantics in `OutboxDispatcher`:
   - retryable failures remain `PENDING`
   - failures that reach the retry threshold are marked `FAILED`
2. Add queue indexes for:
   - `(status, created_at)`
   - `(status, last_attempted_at)`
3. Add integration proof for the terminal failure transition.

## Result

The outbox queue now has a real terminal-state contract instead of infinite reprocessing for poison rows, and the dispatcher's claim query is backed by an index that matches the hot path.
