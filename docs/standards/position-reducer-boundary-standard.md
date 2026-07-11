# Position Reducer Boundary Standard

The position calculator must keep deterministic position transition rules and backdated replay
decision planning pure, typed, and independently testable.

## Responsibilities

`portfolio_transaction_processing_service.app.domain.position_reducer` owns:

1. position balance state transitions for buy and sell events,
2. cash movement amount and booked-cost deltas,
3. transfer, rights, merger, exchange, replacement, spin-off, and demerger quantity behavior,
4. same-instrument corporate-action quantity restatement behavior,
5. FX contract open/close and FX cash settlement position behavior,
6. flat-position residual cost-basis zeroing,
7. effective completed-date selection for backdated replay decisions,
8. replay watermark planning for original backdated transactions.

`portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow`
owns:

1. epoch-fencing checks,
2. repository reads and writes,
3. position history deletion and persistence,
4. deterministic current-epoch rebuild ordering,
5. metric emission,
6. compatibility adaptation between existing DTOs and the pure reducer state.

## Boundary Rules

The reducer must not import database sessions, SQLAlchemy, repositories, outbox repositories,
metrics, epoch-fencing orchestration, persistence models, Pydantic DTOs, or request correlation
context.

The orchestration module must not reintroduce reducer-owned transaction-type sets, cash delta
helpers, buy/sell/transfer/corporate-action state helpers, or private backdated replay decision
helpers. It must not depend on an outbox repository or publish `ReprocessTransactionReplay`;
backdated position recovery is an inline caller-owned transaction.

Backdated replay planning must be deterministic from:

1. event epoch,
2. transaction date,
3. current watermark date,
4. latest position history date,
5. latest completed snapshot date.

## Enforcement

`make architecture-guard` runs `scripts/quality/position_reducer_boundary_guard.py`.

## Compatibility

This is an in-process modularity rule. It preserves `PositionCalculationWorkflow.calculate(...)`,
`PositionCalculationWorkflow.calculate_next_position(...)`, database schema, repository contracts,
epoch-fencing behavior, deterministic history ordering, and public API behavior. The retired,
runtime-inactive internal replay event is intentionally removed; the unified operator replay
request path remains unchanged.
