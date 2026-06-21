# CR-1144 Position Calculator Orchestration Boundary

Date: 2026-06-22

## Scope

Position-state replay orchestration in
`src/services/calculators/position_calculator/app/core/position_logic.py`.

## Finding

`PositionCalculator.calculate(...)` mixed epoch fencing, current state loading, latest snapshot and
position-history boundary reads, original backdated detection, epoch bumping, stale-fence handling,
historical replay event construction, deterministic replay ordering, outbox publication, normal
position-history deletion/replay, position persistence, watermark rearming, and operational logging
in one C-ranked calculator method.

Radon reported:

- `PositionCalculator.calculate`: `C (16)`

## Action Taken

Extracted focused helpers for:

- epoch fence validation,
- effective completed-date resolution,
- original backdated replay detection,
- backdated replay logging and stale-fence handling,
- deterministic replay event construction,
- replay outbox publication,
- normal position-history recalculation,
- position persistence and valuation/timeseries rearming.

The epoch semantics, replay ordering key, outbox topic, correlation propagation, repository write
sequence, and watermark rearming behavior remain unchanged.

## Evidence

Focused unit behavior proof:

- `python -m pytest tests\unit\services\calculators\position_calculator\core\test_position_logic.py -q`
- Result: `47 passed`

Focused integration proof:

- `python -m pytest tests\integration\services\calculators\position_calculator\test_int_reprocessing_atomicity.py -q`
- Result: `3 passed`

Focused static proof:

- `python -m ruff check src/services/calculators/position_calculator/app/core/position_logic.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/calculators/position_calculator/app/core/position_logic.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/calculators/position_calculator/app/core/position_logic.py -s --exclude "*/build/*"`
- Result: `PositionCalculator.calculate` is `A (3)`

Measured movement:

- `PositionCalculator.calculate`: `C (16)` -> `A (3)`

## Residual Risk

This slice does not change transaction-domain methodology, position arithmetic, cash-position
quantity logic, cost-basis formulas, Kafka topic selection, or repository contracts. Remaining
B-ranked helpers in `position_logic.py` should be reviewed separately by measured calculation risk.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of epoch and replay control flow,
- isolation of deterministic replay evidence construction,
- separation of persistence/rearming side effects from orchestration,
- direct proof through unit and focused integration tests.

It does not claim full bank-buyable readiness for `lotus-core`.
