# Position Reducer Boundary Standard

The position calculator must keep deterministic position transition rules and backdated replay
decision planning pure, typed, and independently testable.

## Responsibilities

`portfolio_transaction_processing_service.app.domain.position.reducer` owns:

1. position balance state transitions for buy and sell events,
2. cash movement amount and booked-cost deltas,
3. transfer, rights, merger, exchange, replacement, spin-off, and demerger quantity behavior,
4. same-instrument corporate-action quantity restatement behavior,
5. FX contract open/close and FX cash settlement position behavior,
6. flat-position residual cost-basis zeroing,
7. effective completed-date selection for backdated replay decisions,
8. replay watermark planning for original backdated transactions.

`portfolio_transaction_processing_service.app.application.position_history` owns:

1. one-load epoch-fencing decisions,
2. current versus backdated materialization decisions,
3. replay-window coordination and compare-and-set epoch advancement,
4. deterministic history construction through domain policy,
5. caller-owned transaction sequencing through ports.

`app/ports/position_history.py` owns repository, recalculation-state, and observation contracts.
`app/infrastructure/sqlalchemy_position_history_repository.py`,
`sqlalchemy_position_recalculation_state_store.py`, and
`prometheus_position_history_observer.py` own SQLAlchemy mapping, persistence, shared state access,
metrics, and structured support logs.

## Boundary Rules

The reducer must not import database sessions, SQLAlchemy, repositories, outbox repositories,
metrics, epoch-fencing orchestration, persistence models, Pydantic DTOs, or request correlation
context.

The application module must not reintroduce reducer-owned transaction-type sets, cash delta
helpers, buy/sell/transfer/corporate-action state helpers, or private backdated replay decision
helpers. It must not import SQLAlchemy, ORM models, event DTOs, metrics, logging, or concrete
repositories. It must not depend on an outbox repository or publish `ReprocessTransactionReplay`;
backdated position recovery remains an inline caller-owned transaction.

Backdated replay planning must be deterministic from:

1. event epoch,
2. transaction date,
3. current watermark date,
4. latest position history date,
5. latest completed snapshot date.

## Enforcement

`make architecture-guard` runs `scripts/quality/position_reducer_boundary_guard.py`.
The guard also rejects flat `domain/position_reducer.py` and `domain/position_history.py` modules;
position domain policy belongs under the cohesive `domain/position/` package. It requires the
application processor and its repository, state-store, and observer ports, and rejects framework,
persistence, event DTO, concrete adapter, telemetry, and logging dependencies from that module.

## Compatibility

This is an in-process modularity rule. The production unit of work now calls
`PositionHistoryProcessor` with `BookedTransaction` directly. Public APIs, event contracts,
database schema, caller-owned commit/rollback behavior, epoch semantics, deterministic history
ordering, and downstream cashflow rebuild inputs are unchanged. The former workflow and repository
are retired; the boundary guard rejects either legacy module if it returns.
