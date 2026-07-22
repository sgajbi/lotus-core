# CR-1647 Dividend Withholding Settlement Economics

## Status

Locally implementation-complete on `feat/dividend-withholding-economics`, based on exact main
`b49f05d127ad4d9a1d5660753ac28dfa13fa1bc9`. The runtime/contracts/tests are preserved in signed
commit `27a0ca044188c53826416b6b6a1ff004b94f1975`; this evidence commit, PR review, protected CI,
merge, exact-main validation, and wiki publication remain pending. Issue #448 remains open because
this is only its source-recorded withholding-amount slice.

## Objective and bounded scope

Current ordinary DIVIDEND booking now calculates settlement cash as:

`gross_transaction_amount - withholding_tax_amount - resolved transaction fee`

The implementation reuses the existing nullable event, persistence, ingestion, and query field.
Withholding remains separate source evidence; Core does not infer a rate, jurisdiction, treaty, or
tax advice. Generated cash legs and product cashflows consume the same transaction-domain result.

The slice fails closed before financial work when recorded withholding is negative, above gross, or
consumes all available proceeds. Stable reason codes are `DIVIDEND_014`, `DIVIDEND_015`, and
`DIVIDEND_013` respectively. Governed ingestion schemas already reject negative values before
publishing; `DIVIDEND_014` is defense in depth for direct domain adapters.

## Compatibility and no-claim boundary

Null and zero withholding preserve the previous gross-minus-fee result. No field, event version,
topic, database schema, or migration changed. Historical rebuild retains its explicit legacy
arithmetic and does not silently restate accepted rows.

This slice does not implement a supplied net-dividend identity, withholding-rate derivation or
tolerance, other receipt deductions, jurisdiction policy, return-of-capital classification, basis
reduction, advanced ex/record/payment-date policy, late-link reconciliation, or historical
backfill. Those acceptance areas remain under #448; this evidence does not claim umbrella closure.

## Pattern review and implementation evidence

- The canonical settlement resolver in
  `domain/transaction/settlement/cash_movement.py` remains the single owner used by generated cash
  legs and product cashflows.
- The neighboring INTEREST path already subtracts withholding and other deductions before fees;
  its independent contract manifest was rerun rather than changed.
- Ingestion and query DTOs already carried the withholding field. Their schema descriptions now
  state DIVIDEND/INTEREST applicability and the source-evidence boundary.
- The independent DIVIDEND and ordinary-settlement vector packs now include withholding inputs and
  exact Decimal reconciliation.
- Application-boundary tests prove stable non-retryable rejections, source-safe diagnostics,
  rollback, and absence of cost, position, cashflow, or commit work.
- Database-backed generated-leg and rejection tests were updated for the new arithmetic. They were
  not executed locally because this lane is prohibited from touching Docker; protected GitHub CI
  remains required before merge.
- No dead compatibility path was removed: the historical-rebuild arithmetic is intentional replay
  compatibility, while the current-booking path is the corrected policy.

## Validation

- Warning-strict touched-surface pack: 169 passed.
- Warning-strict `transaction-dividend-contract`: 299 passed.
- Warning-strict `transaction-interest-contract`: 323 passed.
- Pinned Ruff 0.15.18 check and format check passed for every changed Python file.
- Both changed JSON vector packs parsed successfully; `git diff --check` passed.
- Full `make architecture-guard` chain passed, including domain/application/infrastructure
  boundaries, testability, modularity, mapping, repository, and transaction-replay guards.
- Wiki, front-door, architecture-documentation, RFC-status, supported-features,
  incident-playbook, test-lane, and transaction-capability guards passed.
- Exact-worktree wiki parity precheck reported three expected source changes under
  `-AllowUnpublishedSourceChanges`; publish after merge and then run strict parity.

## Documentation decisions

Repository context, RFC slice/conformance truth, operator rejection guidance, supported-feature
status, OpenAPI descriptions, and repo-authored wiki pages changed because runtime and contract
truth changed. No README change is needed because setup, entry points, and contributor workflow are
unchanged. No migration is needed because the existing nullable persisted field is reused.
