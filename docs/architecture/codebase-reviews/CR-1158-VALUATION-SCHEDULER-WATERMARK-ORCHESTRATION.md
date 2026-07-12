# CR-1158 Valuation Scheduler Watermark Orchestration

Date: 2026-06-22

## Scope

- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`

## Finding

After CR-1155, `ValuationScheduler._advance_watermarks(...)` still retained B-ranked orchestration
for latest business-date lookup, lagging state loading, terminal reprocessing loading, first-open
date loading, active-key metric calculation, terminal normalization, and lagging watermark advance
delegation.

The method was no longer a blocker, but keeping input loading and metric observation inline made the
public watermark orchestration harder to scan.

## Action

Extracted focused helpers for:

- watermark-advance input loading,
- active reprocessing key metric observation.

`_advance_watermarks(...)` now coordinates repository construction, input availability, terminal
normalization, and optional lagging-state advancement only.

## Measured Signal

- Before: `ValuationScheduler._advance_watermarks(...)` was `B (6)`.
- After: `ValuationScheduler._advance_watermarks(...)` is `A (3)`.
- `valuation_scheduler.py` has no B-or-worse functions/classes.

## Validation

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
  - `20 passed`
- `python -m ruff check src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
  - passed
- `python -m ruff format src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
  - passed
- `python -m radon cc src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py -s --exclude "*/build/*"`
  - every function/class in `valuation_scheduler.py` is A-ranked

## Residual Risk

No scheduler complexity hotspot remains in this module-level scan. Runtime reliability still depends
on repository correctness, durable job semantics, Kafka delivery behavior, and integration evidence
from the broader valuation orchestration path.

