# CR-292: DLQ replayer commit gating

Date: 2026-03-14

## Summary
- Hardened `tools/dlq_replayer.py` so a replayed DLQ message is committed only after replay
  delivery is actually acknowledged by Kafka.

## Problem
- `DLQReplayConsumer.process_message(...)` republished the original message, called
  `flush(timeout=5)`, logged success, and committed the DLQ offset.
- But positive `flush(...)` results were ignored.
- That meant the replayer tool could:
  - fail to get Kafka delivery confirmation for the replay
  - still commit the DLQ message
  - and silently lose the recovery opportunity

## Change
- Treated positive `flush(timeout=5)` results as an explicit replay failure.
- The tool now commits the DLQ message only after replay delivery is actually accounted for.
- If replay delivery confirmation times out:
  - the tool logs failure
  - the DLQ message is left uncommitted
  - rerunning with the same consumer group can replay it again

## Why this matters
- This tool is used during operational recovery, when correctness matters more than convenience.
- False replay success in a recovery tool is exactly the kind of sharp edge that burns operators
  during incidents.
- This change keeps the tool aligned with the same delivery-accounting standard we now enforce in
  the app runtime.

## Evidence
- Integration proofs:
  - `tests/integration/tools/test_dlq_replayer.py`
  - proves:
    - normal replay still republishes correctly
    - malformed DLQ messages are still skipped
    - replay flush timeout leaves the DLQ message uncommitted, because rerunning the tool with the
      same consumer group replays the same message again successfully

## Validation
- `python -m pytest tests/integration/tools/test_dlq_replayer.py -q`
- `python -m ruff check tools/dlq_replayer.py tests/integration/tools/test_dlq_replayer.py`

## Follow-up
- The next worthwhile move is to review any remaining operator or recovery tools that still commit
  source messages based on best-effort publish attempts rather than confirmed delivery.
