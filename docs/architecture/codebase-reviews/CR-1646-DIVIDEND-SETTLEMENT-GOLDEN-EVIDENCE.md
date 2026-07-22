# CR-1646 Dividend Settlement Golden Evidence

## Status

Hardened locally on `feat/transaction-lifecycle-correctness`; issue #731 remains open for the
broader independent transaction-economics oracle.

## Objective and bounded scope

This slice adds a reusable, implementation-independent regression pack for the currently supported
DIVIDEND settlement boundary:

- gross dividend cash less the resolved transaction fee;
- settlement/payment-date income cashflow with canonical `EOD` cashflow timing and positive signed
  amount;
- no position quantity, trade cost-basis, or local cost-basis change;
- explicit zero trade and local realized P&L;
- exact Decimal arithmetic for a high-precision amount.

The same-pattern scan found fee-equal and fee-dominated rejection vectors already covered by
`ordinary_settlement_cash.v1.json`; this pack deliberately does not duplicate those vectors.
The review fix-forward scan also found the same unsupported `PAYMENT_DATE` timing pattern in the
INTEREST golden oracle, so that #731 oracle test now uses `CashflowTiming.EOD` and asserts the
fixture-owned canonical timing as well.

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
- Primary review findings from #731 comment `5044729433` were fixed forward without rewriting
  signed commit `423fcf042`: the DIVIDEND oracle now uses `CashflowTiming.EOD`, asserts the
  emitted timing separately from the settlement/payment date, carries each vector fee into the
  production cost-basis input boundary, and reconciles fixture-owned trade/local basis plus
  trade/local realized P&L expected values.

## Validation

- `python -W error -m pytest -p no:benchmark tests/unit/transaction_specs/test_dividend_settlement_golden_vectors.py tests/unit/transaction_specs/test_interest_settlement_golden_vectors.py tests/unit/transaction_specs/test_dividend_slice0_characterization.py tests/unit/transaction_specs/test_interest_slice0_characterization.py -q`
  -> 26 passed.
- `python scripts\quality\test_manifest.py --suite transaction-dividend-contract --quiet`
  -> 286 passed.
- `python scripts\quality\test_manifest.py --suite transaction-interest-contract --quiet`
  -> 317 passed.
- `C:\Users\Sandeep\projects\lotus-core\.venv\Scripts\python.exe -m ruff check tests/test_support/transaction_economics_reference.py tests/unit/transaction_specs/test_dividend_settlement_golden_vectors.py tests/unit/transaction_specs/test_interest_settlement_golden_vectors.py`
  -> passed with pinned Ruff 0.15.18.
- `C:\Users\Sandeep\projects\lotus-core\.venv\Scripts\python.exe -m ruff format --check tests/test_support/transaction_economics_reference.py tests/unit/transaction_specs/test_dividend_settlement_golden_vectors.py tests/unit/transaction_specs/test_interest_settlement_golden_vectors.py`
  -> passed.
- JSON fixture parse for `dividend_settlement.v1.json` and `interest_settlement.v1.json` -> passed.
- `git diff --check -- <changed #731 oracle files>` -> passed; Git reported CRLF working-copy
  warnings only.
- The plain warning-strict command is currently blocked before collection by an environment-level
  `pytest_benchmark` `datetime.utcnow()` deprecation warning; the repository test body is warning
  strict with that unrelated plugin disabled.
- The repository-native Ruff wrapper correctly failed closed because the active interpreter has
  Ruff 0.15.22 while `requirements/ci-tooling.lock.txt` requires 0.15.18; the pinned existing
  interpreter above was used for lint and format proof without changing source.
- Wiki decision: no repo-local wiki source change. This is test evidence only and does not change
  operator-facing behavior or support guidance.
