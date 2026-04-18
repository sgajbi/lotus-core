# CR-230 Early Idempotency Fence Review

## Scope

Review the event-consumer idempotency boundary for durable ledger mutations, outbox emission,
pipeline-stage updates, valuation scheduling, and reconciliation execution.

## Finding

The repository already had a schema-backed uniqueness fence on
`processed_events(event_id, service_name)`, but several high-value consumers still used a
two-step pattern:

1. check `is_event_processed(...)`
2. perform durable work
3. insert the processed-event fence at the end

That pattern leaves a race window. Two concurrent deliveries can both pass the read check and both
perform side effects before one of them loses the final insert.

For a banking ledger, that is the wrong default. The idempotency fence needs to be claimed at the
start of the same transaction that performs the durable work, so duplicate deliveries fail closed
before mutation.

## Actions Taken

1. Hardened `IdempotencyRepository` so processed-event writes use a schema-backed atomic insert with
   `ON CONFLICT DO NOTHING`.
2. Added `claim_event_processing(...)` as the explicit start-of-transaction fence API.
3. Moved the following consumers from end-of-transaction idempotency marking to start-of-transaction
   claim semantics:
   - `persistence_service` generic persistence consumer
   - `cost_calculator_service`
   - `cashflow_calculator_service`
   - `position_calculator`
   - `valuation_orchestrator_service` price-event and readiness consumers
   - `financial_reconciliation_service` request consumer
   - pipeline-orchestrator processed/cashflow/aggregation/reconciliation completion consumers
4. Kept exceptional secondary status-only paths on atomic `mark_event_processed(...)` where the
   original transaction intentionally rolls back before terminal handling.
5. Updated unit tests to assert the new claim-at-start contract.

## Why This Matters

This change materially improves exactly-once behavior for database state plus transactional outbox
emission:

1. the processed-event fence is now claimed before durable mutation,
2. the fence rolls back automatically if the transaction fails,
3. duplicate deliveries are blocked by the database uniqueness contract rather than best-effort
   Python sequencing,
4. duplicate side effects are prevented earlier on the critical path.

## Residual Risk Still Open

This closes one important race, but it does not by itself make the whole ledger mathematically
error-free. The main remaining correctness program is:

1. push more figure-level invariants into financial reconciliation and characterization suites,
2. keep correction/cancellation/restatement flows append-only and explicitly modeled,
3. add more DB-backed invariant tests tying lots, positions, cashflows, valuations, and timeseries
   totals together for the same portfolio-day-epoch,
4. continue strengthening supportability evidence for stale/backfill/replay runtime behavior,
5. keep load/backpressure/autoscaling proof current against the KEDA and replay-control posture.

## Evidence

- `src/libs/portfolio-common/portfolio_common/idempotency_repository.py`
- `src/services/persistence_service/app/consumers/base_consumer.py`
- `src/services/calculators/cost_calculator_service/app/consumer.py`
- `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`
- `src/services/calculators/position_calculator/app/consumers/transaction_event_consumer.py`
- `src/services/valuation_orchestrator_service/app/consumers/price_event_consumer.py`
- `src/services/valuation_orchestrator_service/app/consumers/valuation_readiness_consumer.py`
- `src/services/financial_reconciliation_service/app/consumers/reconciliation_requested_consumer.py`
- `src/services/pipeline_orchestrator_service/app/consumers/*`
- `tests/unit/libs/portfolio-common/test_idempotency_repository.py`
- `tests/unit/services/financial_reconciliation_service/test_reconciliation_requested_consumer.py`
- `tests/unit/services/valuation_orchestrator_service/consumers/test_valuation_readiness_consumer.py`
- `tests/unit/services/valuation_orchestrator_service/consumers/test_price_event_consumer.py`
- `tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py`
- `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
