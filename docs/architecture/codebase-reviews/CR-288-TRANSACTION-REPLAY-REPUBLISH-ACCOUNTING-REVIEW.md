# CR-288: Transaction replay republish accounting

Date: 2026-03-14

## Summary
- Hardened `ReprocessingRepository.reprocess_transactions_by_ids(...)` so transaction replay now
  reports partial republish failure and flush-timeout uncertainty explicitly instead of flattening
  them into generic runtime exceptions.

## Problem
- `ReprocessingRepository` republishes completed transaction events directly to Kafka in a loop and
  then calls `flush()`.
- Before this change:
  - a synchronous publish failure mid-loop provided no structured truth about the unpublished tail
  - positive `flush()` results were ignored instead of becoming an explicit replay failure
- That made the replay path weaker than the ingestion and reprocessing publish paths we already
  hardened.

## Change
- Added `ReprocessingReplayError` with:
  - `failed_transaction_ids`
  - `published_record_count`
- Added repository-level accounting for:
  - partial republish failure during the loop
  - delivery-confirmation timeout via positive `flush()`
- The repository now raises explicit replay errors that preserve the remaining unpublished
  transaction ids instead of flattening them into a generic exception.

## Why this matters
- This repository is a real runtime replay path used by the reprocessing consumer.
- Replay correctness depends on being honest about:
  - what already got republished
  - what definitely did not
  - when delivery confirmation is uncertain
- That gives operators and downstream control paths better evidence during replay incidents.

## Evidence
- Unit proofs:
  - `tests/unit/libs/portfolio-common/test_reprocessing_repository.py`
  - proves:
    - unpublished-tail reporting on mid-loop republish failure
    - explicit replay failure on flush timeout
- Consumer compatibility proof:
  - `tests/unit/services/calculators/cost_calculator_service/consumer/test_reprocessing_consumer.py`
  - confirms the consumer still works with the hardened repository semantics

## Validation
- `python -m pytest tests/unit/libs/portfolio-common/test_reprocessing_repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_reprocessing_consumer.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/reprocessing_repository.py tests/unit/libs/portfolio-common/test_reprocessing_repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_reprocessing_consumer.py`

## Follow-up
- The next worthwhile step in this area is the same standard on scheduler dispatch loops that still
  use bare `publish_message(...)` plus `flush(...)` with no explicit partial-delivery accounting.
