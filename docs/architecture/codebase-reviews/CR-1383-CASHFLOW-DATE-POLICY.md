# CR-1383 Cashflow Date Policy

- Date: 2026-07-06
- Status: Hardened locally
- GitHub issue: #449
- Control taxonomy: correctness, methodology, modularity, downstream source evidence

## Objective

Make `cashflows.cashflow_date` selection explicit and policy-driven instead of always deriving it
from `TransactionEvent.transaction_date`.

## Finding

`CashflowLogic.calculate(...)` used `transaction.transaction_date.date()` for every generated
cashflow. That embedded temporal business policy inside object assembly and caused settlement,
income, FX value-date, and synthetic-flow cash movements to be grouped on the booking/trade date
even when Core already carried a better source-owned timing field.

## Change

Added a named cashflow-date resolver in the cashflow calculator domain logic:

1. `synthetic_flow_effective_date` wins when present because it is the explicit synthetic-flow
   effective date.
2. `BUY`, `SELL`, `DEPOSIT`, `WITHDRAWAL`, `FX_CASH_SETTLEMENT_BUY`, and
   `FX_CASH_SETTLEMENT_SELL` use `settlement_date` when available.
3. `DIVIDEND` and `INTEREST` use `settlement_date` as the current Core payment/value-date proxy
   because first-class `payment_date` and `value_date` fields are not yet present in
   `TransactionEvent`.
4. Missing source timing fields fall back to `transaction_date` intentionally, preserving legacy
   behavior only when the event lacks the policy source date.

## Compatibility

No API path, DTO field, persistence schema, Kafka topic, event payload, OpenAPI schema, metric name,
or runtime topology changed. The intentional behavior change is limited to generated
`cashflows.cashflow_date` for event types where the incoming event already contains settlement or
synthetic effective timing.

Downstream cashflow movement, projection, timeseries, and proof consumers continue reading the same
`cashflow_date` field, now with explicit Core-owned timing semantics.

## Same-Pattern Scan

Reviewed the cashflow projection and movement methodology, transaction-spec characterization tests,
and temporal vocabulary standard. The adjacent read products already consume `cashflow_date`
consistently, so the hard-coded policy needed to be fixed at generation time rather than papered
over in query consumers.

## Validation

Focused validation before commit:

1. `python -m pytest tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py tests/unit/transaction_specs/test_dividend_slice0_characterization.py tests/unit/transaction_specs/test_interest_slice0_characterization.py -q`
2. `python -m ruff check src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py tests/unit/transaction_specs/test_dividend_slice0_characterization.py tests/unit/transaction_specs/test_interest_slice0_characterization.py`

Pending final slice gates are recorded in the branch evidence before labeling #449 fixed-local.

## Guidance Decision

Repository context and methodology docs were updated because this is repeatable temporal-domain
policy guidance. No platform skill update was needed; the issue exposed a repo-local calculation
policy invariant rather than a new cross-repo execution workflow.
