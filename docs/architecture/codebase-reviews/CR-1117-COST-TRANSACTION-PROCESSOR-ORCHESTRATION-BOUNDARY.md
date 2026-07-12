# CR-1117: Cost Transaction Processor Orchestration Boundary

Date: 2026-06-20

## Scope

`TransactionProcessor.process_transactions(...)` in the cost calculator service still mixed parser
coordination, valid-transaction selection, metric depth calculation, sorted timeline processing,
calculator exception handling, processed-new filtering, error reporting, open-lot output, and
duration metric emission in one C-ranked method. This is a runtime consumer path for cost-basis
recalculation, so the refactor needed to preserve behavior and keep calculator failures observable.

## Change

- Split valid transaction ID resolution, valid transaction selection, processed-new filtering,
  sorted-timeline processing, calculator invocation, and unexpected-error recording into focused
  `TransactionProcessor` helpers.
- Kept parser, sorter, cost-calculator, error-reporter, metric, and disposition-engine behavior
  unchanged.
- Added a regression test proving unexpected calculator exceptions are converted into transaction
  errors, failed new transactions are excluded from processed output, and open-lot quantities still
  return.

## Evidence

Local proof:

- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_transaction_processor.py -q`
- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer tests/unit/services/calculators/cost_calculator_service/engine -q`
- `python -m ruff check src/services/calculators/cost_calculator_service/app/transaction_processor.py tests/unit/services/calculators/cost_calculator_service/consumer/test_transaction_processor.py`
- `python -m ruff format --check src/services/calculators/cost_calculator_service/app/transaction_processor.py tests/unit/services/calculators/cost_calculator_service/consumer/test_transaction_processor.py`
- `make lint`
- `make typecheck`
- `make quality-maintainability-gate`
- `make quality-complexity-gate`
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- `git diff --check`
- Radon reports `TransactionProcessor.process_transactions` reduced from `C (12)` to `A (1)`;
  all extracted helpers are A-ranked and the module remains A-ranked maintainability at `A (59.43)`.

## Follow-Up

Continue reducing cost-calculator runtime hotspots by domain-processing risk. Prioritize remaining
C/B-ranked cost-engine strategy methods only with direct cost-basis, realized P&L, FX, fee, and lot
state regression proof.
