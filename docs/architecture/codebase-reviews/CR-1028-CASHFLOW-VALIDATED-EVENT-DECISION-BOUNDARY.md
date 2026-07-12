# CR-1028: Cashflow Validated Event Decision Boundary

Date: 2026-06-05

## Scope

Reduce cashflow calculator validated-event processing complexity while preserving database
transaction begin, physical idempotency rollback, stale replay commit, epoch-fence rollback,
semantic duplicate commit, non-cash lifecycle commit, cashflow calculation staging, outbox staging,
success commit, and exception rollback behavior.

## Finding

After CR-1027, `CashflowCalculatorConsumer._process_validated_cashflow_event` still mixed
repository construction, physical idempotency, stale replay skip, epoch fencing, semantic
idempotency, transaction-type validation, non-cash lifecycle skip, rule lookup, cashflow staging,
commit, rollback, and exception propagation in one B-ranked method.

## Action

Extracted focused decision helpers for physical/stale-replay early stops, epoch/semantic-duplicate
early stops, and cashflow staging or non-cash lifecycle skipping. The parent method remains the
database transaction boundary and preserves the original commit/rollback semantics.

## Result

`CashflowCalculatorConsumer._process_validated_cashflow_event` improved from `B (7)` to `A (4)`.
The module remains A-ranked maintainability at `A (34.42)`. Follow-up remains to reduce the
retry/DLQ wrapper `_process_message_with_retry` `B (8)`.

## Evidence

- `python -m pytest tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py -q`
  => 21 passed
- `python -m ruff check src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py -s`
  => `_process_validated_cashflow_event` `A (4)` and extracted decision helpers A-ranked
- `python -m radon mi src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py -s`
  => `transaction_consumer.py` `A (34.42)`
- `python -m radon raw src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py`
  => 462 SLOC / 230 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cashflow calculator consumer refactor that
preserves existing validated-event transaction, commit, rollback, and staging semantics.
