# CR-392: Cashflow Rule-Cache Transaction-Type Normalization

Date: 2026-05-28

## Scope

Cashflow calculator consumer rule-cache lookup.

## Finding

`CashflowCalculatorConsumer` keyed cached cashflow rules with `rule.transaction_type.upper()` and
looked up event rules with `transaction_type.upper()`. Padded source values such as ` buy ` could
miss an otherwise valid cashflow rule, force an unnecessary cache refresh, and ultimately route a
valid event toward the missing-rule error path.

## Change

Reused the shared transaction-domain control-code normalizer for both cashflow rule-cache keys and
cashflow rule lookup keys. Added direct consumer coverage proving padded lower-case rule and
request transaction types resolve to the configured rule without an avoidable second refresh.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py -q`
2. `python -m pytest tests/unit/services/calculators/cashflow_calculator_service -q`
3. `python -m ruff check src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a cashflow
calculation reliability and replay-correctness slice.
