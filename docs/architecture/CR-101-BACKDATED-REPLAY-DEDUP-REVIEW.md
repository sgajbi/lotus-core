## CR-101: Back-dated replay duplicate-trigger deduplication

Date: 2026-03-12
Status: Hardened

### Finding
When a back-dated original transaction triggered epoch bump and replay, `PositionCalculator.calculate(...)` always appended the triggering event after loading historical transactions from the database. If the triggering transaction had already been persisted to the canonical transaction table, it was replayed twice in the same epoch.

### Fix
Deduplicated the replay batch by `transaction_id` before appending the triggering event, preserving deterministic ordering while preventing double replay of the same canonical transaction.

### Follow-up
If future replay flows can legitimately emit the same `transaction_id` with different semantic payloads, deduplication must move to a stronger replay-key contract. For the current canonical transaction model, `transaction_id` is the correct replay identity.

### Evidence
- `src/services/calculators/position_calculator/app/core/position_logic.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
