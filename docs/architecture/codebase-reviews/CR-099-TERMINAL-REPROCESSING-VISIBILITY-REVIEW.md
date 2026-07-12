## CR-099: Terminal reprocessing normalization visibility

Date: 2026-03-12
Status: Hardened

### Finding
CR-098 corrected stale terminal `REPROCESSING` rows by normalizing them back to `CURRENT`, but the normalization path still treated partial success as routine. Because `bulk_update_states(...)` is epoch-fenced, terminal normalization can legitimately skip stale rows once a newer epoch already exists. That is safe, but leaving it silent weakens runtime diagnosability in the same way CR-097 previously did for watermark advancement.

### Fix
Updated `ValuationScheduler._advance_watermarks(...)` to warn when fewer terminal reprocessing states are normalized than were prepared, including prepared count, updated count, stale-skipped count, and sample keys.

### Follow-up
If this path becomes operationally noisy, surface the skipped count as explicit telemetry rather than removing the warning.

### Evidence
- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
