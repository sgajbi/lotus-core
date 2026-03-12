## CR-100: Reprocessing fan-out stale skip visibility

Date: 2026-03-12
Status: Hardened

### Finding
`ReprocessingWorker` fans out watermark resets across all portfolios holding a security, but its success logging treated partial updates as routine success. Because `PositionStateRepository.update_watermarks_if_older(...)` can legitimately skip rows when newer or already-older state exists, epoch/current-state fencing could silently reduce the actual fan-out without any runtime signal.

### Fix
Updated `ReprocessingWorker._process_batch()` to warn when fewer watermark resets are applied than were targeted, including targeted count, updated count, stale-skipped count, and sample keys.

### Follow-up
If this path becomes noisy in production, expose the skipped count as explicit telemetry instead of removing the warning.

### Evidence
- `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`
