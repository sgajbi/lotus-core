## CR-103: Replay outbox correlation preservation

Date: 2026-03-12
Status: Hardened

### Finding
The back-dated replay path created durable outbox events without explicitly propagating the active correlation context into the outbox row. That meant the replay payload could be correct while the durable outbox lineage still lost the triggering correlation id.

### Fix
Updated `PositionCalculator.calculate(...)` to persist the active `correlation_id_var` value on replay outbox events when present, and added both unit and DB-backed integration coverage proving the outbox rows retain that correlation.

### Follow-up
Apply the same durability test pattern to any other outbox-backed replay or fan-out path that currently relies on ambient context rather than explicit outbox correlation propagation.

### Evidence
- `src/services/calculators/position_calculator/app/core/position_logic.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- `tests/integration/services/calculators/position_calculator/test_int_reprocessing_atomicity.py`
