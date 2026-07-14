# Developer Guide: Position History Processing

Position history is an in-process capability of `portfolio_transaction_processing_service`. It
materializes the auditable quantity and cost-basis state for each portfolio/security transaction
stream. There is no standalone position-calculator runtime or source package.

## Architecture

The dependency flow is:

```text
Kafka delivery mapper
  -> ProcessTransactionUseCase
  -> PositionHistoryProcessingPort
  -> PositionHistoryProcessor
  -> position domain policies
  -> PositionHistoryRepository / PositionRecalculationStateStore / PositionHistoryObserver
  -> SQLAlchemy and Prometheus infrastructure adapters
```

Capability ownership is explicit:

- `app/domain/position/` owns immutable position state, history construction, transaction effects,
  and deterministic backdated-recalculation decisions.
- `app/domain/transaction/` owns the framework-neutral booked transaction and semantic identity.
- `app/application/position_history.py` coordinates current and backdated materialization through
  ports while preserving the caller-owned transaction.
- `app/ports/position_history.py` defines persistence, recalculation-state, and observation
  contracts.
- `app/infrastructure/position/history_repository.py` and
  `position/recalculation_state.py` map domain records to durable state.
- `app/infrastructure/position/observability.py` owns metrics and support logs.

Domain and application code must not import Kafka/Pydantic event DTOs, SQLAlchemy models or
sessions, concrete repositories, metrics, or logging. Service-owned behavior must not be added to
`portfolio_common`; move it into the capability package once production-consumer inventory proves
there is only one owner.

## Extending Position Semantics

When a governed transaction type changes position quantity or basis:

1. Define or update its transaction vocabulary and validation in the owning transaction-domain
   family.
2. Add the deterministic state transition to `app/domain/position/reducer.py` using domain
   language and immutable inputs/outputs.
3. Add direct domain tests under
   `tests/unit/services/portfolio_transaction_processing_service/domain/position/` for current,
   backdated, transfer, corporate-action, cash-position, FX, zero-balance, and invalid cases that
   apply.
4. Add processor or PostgreSQL proof when the change affects replay windows, epoch fencing,
   locking, rollback, persistence mapping, or downstream rebuild inputs.
5. Update the transaction specification, supported-feature evidence, and operator documentation
   when behavior or supportability truth changes.

Do not add transaction-type conditionals to delivery, repositories, or telemetry adapters. Do not
restore `position_calculation_workflow.py`, `position_repository.py`, or a standalone calculator
consumer.

## Validation

Run the focused proofs from the repository root:

```powershell
python -m pytest tests/unit/services/portfolio_transaction_processing_service/domain/position tests/unit/services/portfolio_transaction_processing_service/application/test_position_history.py -q
python -m pytest tests/integration/services/portfolio_transaction_processing_service/test_int_position_history_repository.py tests/integration/services/portfolio_transaction_processing_service/test_int_position_reprocessing_atomicity.py tests/integration/services/portfolio_transaction_processing_service/test_int_position_recalculation_concurrency.py -q
make architecture-guard
```

Use the repository-native feature and PR gates before delivery. The focused tests supplement those
gates; they do not replace them.
