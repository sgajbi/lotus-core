# CR-462: Transaction Interest Event Economics Guard

Date: 2026-05-28

## Scope

Shared `TransactionEvent` validation and cashflow-calculator consumer handling for malformed
interest deduction and net-interest economics.

## Finding

`TransactionEvent` already rejected negative core amounts and non-positive FX/rate fields after
CR-461, but direct event construction could still accept negative interest-specific economic
fields such as `withholding_tax_amount`, `other_interest_deductions_amount`, and
`net_interest_amount`.

The cashflow calculator uses those fields directly when calculating `INTEREST` cashflows. A
negative deduction would inflate the derived net interest cashflow, while a negative net interest
amount would make the event contract weaker than the ingestion DTO and transaction-domain
validation posture.

## Change

Extended the shared event-boundary nonnegative amount guard to include:

1. `withholding_tax_amount`,
2. `other_interest_deductions_amount`,
3. `net_interest_amount`.

Added direct shared-model proof and cashflow-consumer proof that a Kafka payload with a negative
interest deduction is rejected by `TransactionEvent` validation and sent to DLQ before idempotency,
rule loading, cashflow persistence, or outbox publication begins.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
3. `python -m pytest tests/unit/services/calculators/cashflow_calculator_service -q`
4. `python -m pytest tests/unit/services/persistence_service -q`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/events.py tests/unit/libs/portfolio_common/test_transaction_event_control_code_model.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py`
7. `git diff --check`

Results:

1. Focused event/cashflow proof: `28 passed`
2. Portfolio-common unit pack: `479 passed`
3. Cashflow-calculator unit pack: `58 passed`
4. Persistence-service unit pack: `15 passed`
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
shared transaction event boundary now fails closed for interest deduction values that would
otherwise distort cashflow economics.
