# CR-297: Reprocessing tool flush truth

Date: 2026-03-14

## Summary
- Hardened `tools/reprocess_transactions.py` so final producer flush is treated as delivery accounting,
  not best-effort cleanup.

## Problem
- The tool logged:
  - `Completed reprocessing. Republished N events.`
- before evaluating its final `kafka_producer.flush(timeout=10)` outcome.
- That meant the tool could overstate replay success if Kafka still had undelivered buffered messages.
- The final flush also mattered on the failure path because the repository can raise after some earlier
  publishes were already queued, so the cleanup flush is not redundant.

## Change
- Added `_flush_or_raise(...)` to make final producer flush outcome explicit.
- Reworked `main(...)` so:
  - success logging happens only after a zero-undelivered final flush
  - failure-path flush remains best-effort cleanup and does not mask the original replay error
- Kept the cleanup flush because it is still needed to account for earlier queued messages after a
  later partial replay failure.

## Why this matters
- This is operator recovery tooling.
- Recovery tools should not claim success before delivery confirmation is accounted for.
- The change also preserves the original replay failure when cleanup flush itself later reports
  undelivered messages.

## Evidence
- Unit proofs:
  - `tests/unit/tools/test_reprocess_transactions.py`
  - proves:
    - empty input still exits early
    - successful replay with undelivered final flush raises and suppresses false success logging
    - replay failure remains the raised exception even if cleanup flush also reports undelivered
      messages

## Validation
- `python -m pytest tests/unit/tools/test_reprocess_transactions.py -q`
- `python -m ruff check tools/reprocess_transactions.py tests/unit/tools/test_reprocess_transactions.py`

## Follow-up
- The next worthwhile move is to review the remaining service lifecycle hooks for the same standard:
  never log producer flush success until the undelivered count is actually zero.
