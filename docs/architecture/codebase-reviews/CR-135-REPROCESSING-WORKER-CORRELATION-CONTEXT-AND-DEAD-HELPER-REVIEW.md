## CR-135 - Reprocessing Worker Correlation Context and Dead Helper Review

### Findings
1. `ReprocessingWorker` processed durable `RESET_WATERMARKS` jobs without setting the job's durable `correlation_id` into the active logging context. The durable replay chain preserved lineage on disk, but the worker step itself did not execute under that lineage.
2. `ValuationRepositoryBase.find_portfolios_for_security(...)` was dead after the replay fanout became date-aware. Only tests still referenced it.

### Fixes
- `ReprocessingWorker` now sets `correlation_id_var` from `job.correlation_id` while processing each claimed durable replay job and restores the prior context afterward.
- Added unit proof that the worker executes under the job correlation context and restores ambient state.
- Removed the dead `find_portfolios_for_security(...)` helper and its obsolete test coverage.

### Why it matters
- Durable replay lineage is only fully useful if each runtime step actually executes under that lineage.
- Dead replay helpers create false alternate ownership and weaken the signal of the real business contract, which is now date-aware fanout.

### Evidence
- `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`
- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`
