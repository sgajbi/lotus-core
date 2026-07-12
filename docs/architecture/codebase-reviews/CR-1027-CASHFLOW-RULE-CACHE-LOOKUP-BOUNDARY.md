# CR-1027: Cashflow Rule Cache Lookup Boundary

Date: 2026-06-05

## Scope

Reduce cashflow calculator rule-cache lookup complexity while preserving transaction-type
normalization, TTL freshness behavior, lazy cache loading, double-checked locking, missing-rule
immediate refresh, cache invalidation behavior, and concurrent refresh protection.

## Finding

`CashflowCalculatorConsumer._get_rule_for_transaction` mixed transaction-type normalization,
fresh-cache probing, cache-lock acquisition, stale-cache reload, in-lock lookup, missing-rule
refresh logging, forced reload, and final lookup in one B-ranked method.

## Action

Added focused helpers for fresh cached rule lookup, direct cache lookup, stale/missing cache
refresh, and missing-rule reload. The public cache method keeps the lock ownership and global cache
mutation boundary so the existing concurrency behavior remains explicit.

## Result

`CashflowCalculatorConsumer._get_rule_for_transaction` improved from `B (7)` to `A (3)`. The
module remains A-ranked maintainability at `A (36.32)`. Follow-up remains to reduce
`_process_message_with_retry` `B (8)` and `_process_validated_cashflow_event` `B (7)`.

## Evidence

- `python -m pytest tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py -q`
  => 21 passed
- `python -m ruff check src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py tests\unit\services\calculators\cashflow_calculator_service\unit\consumers\test_cashflow_transaction_consumer.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py -s`
  => `_get_rule_for_transaction` `A (3)` and all cache lookup helpers A-ranked
- `python -m radon mi src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py -s`
  => `transaction_consumer.py` `A (36.32)`
- `python -m radon raw src\services\calculators\cashflow_calculator_service\app\consumers\transaction_consumer.py`
  => 401 SLOC / 220 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cashflow calculator consumer refactor that
preserves existing rule-cache TTL, missing-rule refresh, invalidation, and concurrency semantics.
