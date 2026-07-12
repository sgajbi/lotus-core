# CR-019 Financial Engine Model Surface Review

## Scope

Remaining financial-engine model files after the engine runtime and config
cleanup.

## Findings

The remaining model surface was split into:

- `core/models/transaction.py`
- `core/models/request.py`
- `core/models/response.py`

Only `Transaction` was genuinely live shared domain vocabulary.

`request.py` and most of `response.py` were leftovers from a standalone
transaction-processing API shape that no longer exists in `lotus-core`.

Live usage was limited to:

- `Transaction`
- `ErroredTransaction`

`TransactionProcessingRequest` and `TransactionProcessingResponse` had no live
production or test consumers.

## Actions taken

- Replaced the vague top-level `core/` and `logic/` import surface with a real
  `domain/` and `processing/` structure for the live code.
- Updated cost-calculator service and tests to import the namespaced package
- Removed dead standalone-API files:
  - `core/models/request.py`
  - `core/models/response.py`
- Removed the obsolete generic source files under `core/` and `logic/`

## Rationale

The engine should contain only live domain models and processing logic.

Dead API wrapper models and vague top-level module names create false
architectural signals and make ownership harder to understand. The remaining
engine is shared domain/process logic, so it should look like a proper package.

## Follow-up

Service ownership was finalized later in CR-020 once production usage confirmed
the engine was no longer truly shared.

## Evidence

- `src/services/calculators/cost_calculator_service/app/cost_engine/domain/models/transaction.py`
- `src/services/calculators/cost_calculator_service/app/cost_engine/domain/models/error.py`
- `src/services/calculators/cost_calculator_service/app/cost_engine/processing/error_reporter.py`
- `src/services/calculators/cost_calculator_service/app/transaction_processor.py`
