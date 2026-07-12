# CR-1323 Position Reducer Boundary

## Scope

Issue cluster: GitHub issue #627.

This slice splits deterministic position transition rules and backdated replay decision planning
from database sessions, repositories, outbox staging, metrics, epoch fencing, and position-history
persistence orchestration.

## Objective

Make buy/sell, cash movement, transfer, corporate-action, spin-off, FX position transitions, and
original-backdated replay decisions testable without `AsyncSession`, repository fakes, outbox
repositories, metrics, epoch-fencing objects, persistence models, or Pydantic DTOs.

## Changes

1. Added `position_reducer.py` with `PositionBalanceState`, `BackdatedReplayDecision`,
   `calculate_next_position_state(...)`, `cash_position_deltas(...)`, and
   `plan_backdated_replay(...)`.
2. Refactored `PositionCalculator.calculate(...)` to read latest state/history/snapshot evidence,
   delegate effective-date and replay-watermark selection to the pure planner, and keep epoch
   fencing, repository writes, outbox staging, metrics, and replay ordering in orchestration.
3. Refactored `PositionCalculator.calculate_next_position(...)` into a compatibility adapter from
   the existing DTO to the pure reducer state and back.
4. Removed reducer-owned transaction-type sets and private buy/sell/cash/transfer/corporate-action
   helpers from `position_logic.py`.
5. Added direct reducer tests using plain objects and dataclasses, plus guard tests for the new
   boundary.
6. Added `scripts/position_reducer_boundary_guard.py` and wired it into
   `make architecture-guard`.
7. Added `docs/standards/position-reducer-boundary-standard.md`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, outbox event payload,
database schema, repository contract, metric name, epoch-fencing behavior, replay ordering,
position-history row field, or public calculator entry point changed.

`PositionCalculator.calculate_next_position(...)` remains available for existing callers and tests.
Its implementation now delegates to the pure reducer.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/calculators/position_calculator/core/test_position_reducer.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py -q`
2. `python -m pytest tests/unit/services/calculators/position_calculator/core/test_position_reducer.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py tests/unit/scripts/test_position_reducer_boundary_guard.py -q`
3. `python scripts/position_reducer_boundary_guard.py`
4. `python -m ruff check <touched position reducer Python paths>`
5. `python -m compileall -q src/services/calculators/position_calculator/app/core/position_logic.py src/services/calculators/position_calculator/app/core/position_reducer.py`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal calculator composition and
testability without changing operator-facing commands, public API behavior, supported features, or
published wiki truth.

No platform skill source change is required in this slice because the existing backend delivery
guidance already covers repeated infrastructure-coupled policy patterns through pure policies,
ports/adapters where needed, focused tests, guards, and repo context.

## Remaining Work

GitHub issue #627 is locally fixed for pure position transition functions, pure backdated replay
planning, orchestration separation, direct reducer tests, persistence/outbox compatibility coverage,
and an architecture guard pending PR CI/QA and issue closure.

Broader position-calculator service packaging and any future migration of the pure reducer into a
shared domain package remain separate issue scope.
