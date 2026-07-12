# CR-1157 Valuation Scheduler Dispatch

Date: 2026-06-22

## Scope

- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`

## Finding

`ValuationScheduler._dispatch_jobs(...)` mixed record-key construction, event DTO construction,
correlation-header policy, Kafka publish calls, partial publish failure flushing, remaining-key
error construction, delivery confirmation flushing, timeout error construction, and success logging
in one B-ranked method.

This made dispatch failure behavior and delivery-confirmation evidence harder to inspect during
operational reliability work.

## Action

Extracted focused helpers for:

- valuation job record-key formatting,
- correlation header construction,
- `PortfolioValuationRequiredEvent` payload construction,
- producer publication,
- partial dispatch failure handling,
- delivery confirmation.

The Kafka topic, message key, event payload, correlation header behavior, producer flush calls, and
error messages are preserved.

## Measured Signal

- Before: `ValuationScheduler._dispatch_jobs(...)` was `B (7)`.
- After: `ValuationScheduler._dispatch_jobs(...)` is `A (5)`.
- `valuation_scheduler.py` now has one remaining B-ranked method:
  - `ValuationScheduler._advance_watermarks(...)`: `B (6)`.

## Validation

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
  - `20 passed`
- `python -m ruff check src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
  - passed
- `python -m ruff format src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
  - passed
- `python -m radon cc src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py -s --exclude "*/build/*"`
  - `ValuationScheduler._dispatch_jobs - A (5)`

## Residual Risk

`_advance_watermarks(...)` remains B-ranked because it still owns the public watermark orchestration
sequence. It is not a C-ranked blocker, but can be reduced further if scheduler maintainability
remains the next target.

