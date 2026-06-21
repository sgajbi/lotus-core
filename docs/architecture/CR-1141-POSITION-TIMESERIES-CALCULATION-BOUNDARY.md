# CR-1141 Position Timeseries Calculation Boundary

Date: 2026-06-22

## Scope

Daily position timeseries calculation in
`src/services/timeseries_generator_service/app/core/position_timeseries_logic.py`.

## Finding

`PositionTimeseriesLogic.calculate_daily_record(...)` mixed beginning/end market-value extraction,
quantity and average-cost calculation, position-flow bucketing, portfolio-flow bucketing,
position-flow sign normalization, fee extraction, and DTO construction in one C-ranked calculation
method. This calculation is part of portfolio analytics evidence generation, so Decimal-safe
cashflow and average-cost behavior needs to stay reviewable and directly tested.

Radon reported:

- `PositionTimeseriesLogic.calculate_daily_record`: `C (11)`
- `PositionTimeseriesLogic`: `C (12)`

## Action Taken

Extracted focused helpers for:

- beginning market value selection,
- zero-safe average cost,
- expense cashflow classification,
- cashflow bucket accumulation for position and portfolio flows.

Added direct unit coverage proving zero quantity yields zero average cost rather than dividing by
zero or inventing a cost value.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\timeseries_generator_service\timeseries-generator-service\core\test_position_timeseries_logic.py -q`
- Result: `7 passed`

Focused static proof:

- `python -m ruff check src/services/timeseries_generator_service/app/core/position_timeseries_logic.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_position_timeseries_logic.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/timeseries_generator_service/app/core/position_timeseries_logic.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_position_timeseries_logic.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/timeseries_generator_service/app/core/position_timeseries_logic.py -s --exclude "*/build/*"`
- Result: `PositionTimeseriesLogic.calculate_daily_record` is `A (1)`, and every function/class in
  `position_timeseries_logic.py` is A-ranked.

Measured movement:

- `PositionTimeseriesLogic.calculate_daily_record`: `C (11)` -> `A (1)`
- `PositionTimeseriesLogic`: `C (12)` -> `A (2)`
- `position_timeseries_logic.py`: no B-or-worse functions/classes remain

## Residual Risk

This slice does not change position timeseries API contracts, cashflow classification vocabulary,
portfolio aggregation, consumer orchestration, persistence behavior, or event semantics. Broader
timeseries generator consumer and scheduler hotspots remain separate measured work.

## Bank-Buyable Control Movement

This slice improves:

- Decimal-safe calculation reviewability,
- direct proof for zero-quantity average-cost behavior,
- separation of cashflow bucket policy from DTO construction.

It does not claim full bank-buyable readiness for `lotus-core`.
