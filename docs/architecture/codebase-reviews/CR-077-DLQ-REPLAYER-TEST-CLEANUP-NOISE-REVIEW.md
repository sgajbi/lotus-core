# CR-077 DLQ Replayer Test Cleanup Noise Review

## Scope
Remove the last remaining direct cleanup `print(...)` in the test suite outside the shared output-control path.

## Findings
- `tests/integration/tools/test_dlq_replayer.py` still printed topic-deletion cleanup failures directly to stdout during fixture teardown.
- This was low-frequency, but it was still inconsistent with the broader effort to keep healthy test runs quiet and let unusual cleanup issues surface as warnings instead of routine console chatter.

## Changes
1. Replaced the direct `print(...)` in the DLQ replayer topic cleanup path with:
   - `warnings.warn(...)`
2. Kept the cleanup non-fatal so transient Kafka admin cleanup issues do not mask the primary test assertion.

## Validation
- `python -m pytest tests/integration/tools/test_dlq_replayer.py -q`
- `python -m ruff check tests/integration/tools/test_dlq_replayer.py`

## Residual Risk
- This does not change runtime behavior; it only improves signal quality.
- Any future teardown-only diagnostics in tests should follow the same pattern: warnings for anomalous cleanup, not unconditional prints.
