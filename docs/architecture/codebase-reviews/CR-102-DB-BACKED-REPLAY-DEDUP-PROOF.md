## CR-102: DB-backed replay deduplication proof

Date: 2026-03-12
Status: Hardened

### Finding
CR-101 fixed duplicate replay of a persisted triggering transaction at the unit level, but the invariant still needed proof on the real atomic outbox path. Without a DB-backed assertion, the system could regress while still appearing correct under mocks.

### Fix
Added an integration test that persists the triggering back-dated transaction, runs the real atomic replay path, and asserts the outbox batch contains each `transaction_id` only once.

### Follow-up
If future replay batching evolves beyond transaction identity, extend the proof to the stronger replay-key contract rather than relying only on `transaction_id` uniqueness.

### Evidence
- `tests/integration/services/calculators/position_calculator/test_int_reprocessing_atomicity.py`
