# CR-1015: Reprocessing Replay Orchestration Boundary

Date: 2026-06-05

## Scope

Split shared transaction reprocessing replay orchestration into focused transaction-id
normalization, ordered database fetch, no-match logging, correlation-header construction,
per-transaction publish, publish-failure attribution, and flush verification helpers without
changing replay ordering, deduplication, correlation header omission, partial failure reporting, or
flush timeout behavior.

## Finding

`ReprocessingRepository.reprocess_transactions_by_ids` mixed request deduplication, empty-request
handling, SQL ordering construction, database execution, no-match logging, correlation header
construction, event-model conversion, publish logging, Kafka publication, partial-failure
attribution, flush timeout handling, success logging, and count return in one C-ranked method.

## Action

Added focused helpers for ordered unique transaction IDs, ordered replay query construction,
transaction fetch, no-match logging, correlation headers, transaction publish orchestration,
single-transaction publish, publish-failure wrapping, and flush verification. Existing direct
repository tests continue to cover success, no-match handling, requested-order preservation,
deduplication, missing correlation headers, partial publish failure, and flush timeout behavior.

## Result

`ReprocessingRepository.reprocess_transactions_by_ids` improved from `C (11)` to `A (4)`. Every
function, class, and method in `reprocessing_repository.py` now reports A-ranked cyclomatic
complexity, and the module remains A-ranked maintainability at `A (63.20)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_reprocessing_repository.py -q`
  => 7 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\reprocessing_repository.py tests\unit\libs\portfolio-common\test_reprocessing_repository.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\reprocessing_repository.py tests\unit\libs\portfolio-common\test_reprocessing_repository.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\reprocessing_repository.py -s`
  => `ReprocessingRepository.reprocess_transactions_by_ids` `A (4)` and every function/class/method
  in `reprocessing_repository.py` A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\reprocessing_repository.py -s`
  => `reprocessing_repository.py` `A (63.20)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\reprocessing_repository.py`
  => 161 SLOC / 85 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared reprocessing repository refactor that
preserves existing transaction replay semantics.
