# Position Reducer Boundary Standard

The position calculator must keep deterministic position transition rules and backdated replay
decision planning pure, typed, and independently testable.

## Responsibilities

`position_calculator.app.core.position_reducer` owns:

1. position balance state transitions for buy and sell events,
2. cash movement amount and booked-cost deltas,
3. transfer, rights, merger, exchange, replacement, spin-off, and demerger quantity behavior,
4. same-instrument corporate-action quantity restatement behavior,
5. FX contract open/close and FX cash settlement position behavior,
6. flat-position residual cost-basis zeroing,
7. effective completed-date selection for backdated replay decisions,
8. replay watermark planning for original backdated transactions.

`position_calculator.app.core.position_logic` owns:

1. epoch-fencing checks,
2. repository reads and writes,
3. position history deletion and persistence,
4. outbox staging,
5. replay event ordering and publication orchestration,
6. metric emission,
7. compatibility adaptation between existing DTOs and the pure reducer state.

## Boundary Rules

The reducer must not import database sessions, SQLAlchemy, repositories, outbox repositories,
metrics, epoch-fencing orchestration, persistence models, Pydantic DTOs, or request correlation
context.

The orchestration module must not reintroduce reducer-owned transaction-type sets, cash delta
helpers, buy/sell/transfer/corporate-action state helpers, or private backdated replay decision
helpers.

Backdated replay planning must be deterministic from:

1. event epoch,
2. transaction date,
3. current watermark date,
4. latest position history date,
5. latest completed snapshot date.

## Enforcement

`make architecture-guard` runs `scripts/position_reducer_boundary_guard.py`.

## Compatibility

This is an in-process modularity rule. It preserves `PositionCalculator.calculate(...)`,
`PositionCalculator.calculate_next_position(...)`, Kafka topics, outbox event payload shape,
database schema, repository contracts, metric names, epoch-fencing behavior, replay ordering, and
public API behavior.
