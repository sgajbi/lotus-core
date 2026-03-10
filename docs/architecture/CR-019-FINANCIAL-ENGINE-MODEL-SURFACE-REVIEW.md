# CR-019 Financial Engine Model Surface Review

## Scope

Remaining `financial-calculator-engine` core model files after the engine runtime
and config cleanup.

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

- Kept `core/models/transaction.py` as shared engine domain vocabulary
- Extracted the live shared error model into `core/models/error.py`
- Updated engine logic and cost-calculator service orchestration to import from
  `core.models.error`
- Removed dead files:
  - `core/models/request.py`
  - `core/models/response.py`

## Rationale

The shared engine should contain only reusable domain models that are actively
consumed by shared cost-basis logic or its owning service orchestration.

Dead API wrapper models create false architectural signals and increase the
surface area that future engineers have to reason about.

## Follow-up

Review the remaining `core/models/transaction.py` surface only if engine/domain
ownership changes again. It is live and correctly owned today.

## Evidence

- `src/libs/financial-calculator-engine/src/core/models/transaction.py`
- `src/libs/financial-calculator-engine/src/core/models/error.py`
- `src/libs/financial-calculator-engine/src/logic/error_reporter.py`
- `src/services/calculators/cost_calculator_service/app/transaction_processor.py`
