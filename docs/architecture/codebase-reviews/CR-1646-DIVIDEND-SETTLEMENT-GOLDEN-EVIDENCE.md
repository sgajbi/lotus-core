# CR-1646 Dividend Settlement Golden Evidence

## Status

Hardened locally on `feat/transaction-lifecycle-correctness`; issue #731 remains open for the
broader independent transaction-economics oracle.

## Objective and bounded scope

This slice adds a reusable, implementation-independent regression pack for the currently supported
DIVIDEND settlement boundary:

- gross dividend cash less the resolved transaction fee;
- payment-date income cashflow with positive signed amount;
- no position quantity or cost-basis change;
- explicit zero realized P&L;
- exact Decimal arithmetic for a high-precision amount.

The same-pattern scan found fee-equal and fee-dominated rejection vectors already covered by
`ordinary_settlement_cash.v1.json`; this pack deliberately does not duplicate those vectors.

## Compatibility and no-claim boundary

No API, OpenAPI, event, database, migration, persistence, runtime, downstream, or financial-policy
behavior changed. The pack preserves existing supported gross-minus-fee DIVIDEND behavior.

This evidence does not implement or close the broader #448 dividend work. Withholding tax, return of
capital, basis reduction, ex-date/record-date/payment-date policy dimensions, and late-link
reconciliation remain outside this slice. It also does not close #731's PostgreSQL/E2E reuse,
property/metamorphic, mutation, reporting, or remaining-family criteria.

## Implementation evidence

- Fixture: `tests/fixtures/transaction_economics/dividend_settlement.v1.json`
- Independent evaluator: `tests/test_support/transaction_economics_reference.py`
- Conformance tests: `tests/unit/transaction_specs/test_dividend_settlement_golden_vectors.py`
- Reference evaluator import guard rejects `src` and `portfolio_common` roots.
- The test covers settlement, cashflow, position reducer, and cost-basis outputs from one reviewed
  vector set.

## Validation

- `python -W error -m pytest -p no:benchmark tests/unit/transaction_specs/test_dividend_settlement_golden_vectors.py -q`
  -> 6 passed.
- The plain warning-strict command is currently blocked before collection by an environment-level
  `pytest_benchmark` `datetime.utcnow()` deprecation warning; the repository test body is warning
  strict with that unrelated plugin disabled.
- Wiki decision: no repo-local wiki source change. This is test evidence only and does not change
  operator-facing behavior or support guidance.
