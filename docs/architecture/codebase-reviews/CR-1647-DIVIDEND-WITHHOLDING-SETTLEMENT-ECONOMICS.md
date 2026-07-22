# CR-1647 Dividend Withholding Settlement Economics

## Status

Locally implementation-complete on `feat/dividend-withholding-economics`, based on exact main
`b49f05d127ad4d9a1d5660753ac28dfa13fa1bc9`. The runtime/contracts/tests are preserved in signed
commit `27a0ca044188c53826416b6b6a1ff004b94f1975`; self-review hardening is signed through
`260779b7b72275c53b46d46ae7d37b9246b0a684`. Agent 1's application-boundary review finding is
fixed in signed commit `ab7504f4c755c9e7bde81a8c19ad7933ed88cc64`; the same-pattern
transformed/split-output hardening is signed in
`227986d4d11a562cee7981e7e685403b54ebf44e`. Final review, protected CI, merge, exact-main
validation, and wiki publication remain pending. Issue #448 remains open because this is only its
source-recorded withholding-amount slice.

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
topic, database schema, or migration changed. Every transaction output produced by the current
cost-processing step uses current-booking economics even when position processing returns it inside
an inline rebuild, including transformed or split identities. Only previously accepted suffix rows
use the historical-rebuild context and retain legacy arithmetic, so the fix does not silently
restate existing history.

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
- Self-review found the ordinary-settlement oracle initially covered only accepted withholding
  arithmetic. Three implementation-independent vectors now lock negative, over-gross, and
  fully-consumed withholding rejection codes as well.
- Application-boundary tests prove stable non-retryable rejections, source-safe diagnostics,
  rollback, and absence of cost, position, cashflow, or commit work.
- Agent 1's cross-review found that inline rebuild originally classified both the current command
  and prior suffix rows as historical. The application boundary now identifies every current
  cost-processing output by portfolio and transaction identity, applies net-of-withholding current
  economics to it, and keeps legacy gross-minus-fee arithmetic only for a pre-existing suffix row.
  The regression uses a transformed output identity different from the raw command, and also proves
  the current product cashflow equals its generated settlement leg.
- Database-backed generated-leg and rejection tests were updated for the new arithmetic. They were
  not executed locally because this lane is prohibited from touching Docker; protected GitHub CI
  remains required before merge.
- No dead compatibility path was removed: historical-rebuild arithmetic remains intentional replay
  compatibility for previously accepted rows, while every currently accepted command uses the
  corrected policy.

## Validation

- Complete transaction-processing application unit package: 148 passed warning-strict after the
  transformed-current-output hardening.
- Warning-strict touched-surface pack: 172 passed after oracle hardening.
- Warning-strict `transaction-dividend-contract`: 302 passed after oracle hardening.
- Warning-strict `transaction-interest-contract`: 326 passed after oracle hardening.
- Pinned Ruff 0.15.18 check and format check passed for every changed Python file.
- Both changed JSON vector packs parsed successfully; `git diff --check` passed.
- Full `make architecture-guard` chain passed, including domain/application/infrastructure
  boundaries, testability, modularity, mapping, repository, and transaction-replay guards.
- Wiki, front-door, architecture-documentation, RFC-status, supported-features,
  incident-playbook, test-lane, and transaction-capability guards passed.
- Strict MyPy passed across all 237 source files after the review fix; the complete architecture
  guard chain and wiki/docs gate also passed.
- Exact-worktree wiki parity precheck reported three expected source changes under
  `-AllowUnpublishedSourceChanges`; publish after merge and then run strict parity.

## Documentation decisions

Repository context, RFC slice/conformance truth, operator rejection guidance, supported-feature
status, OpenAPI descriptions, and repo-authored wiki pages changed because runtime and contract
truth changed. No README change is needed because setup, entry points, and contributor workflow are
unchanged. No migration is needed because the existing nullable persisted field is reused.
