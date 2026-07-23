# CR-1647 Dividend Withholding Settlement Economics

## Status

Locally implementation-complete on `feat/dividend-withholding-economics`, rebased once onto exact
main `3ed571a1c1b448f2b915d71b3d24131a2d744d52`. The signed runtime, contract, test, self-review,
application-boundary review-fix, and transformed/split-output commits remain patch-equivalent to
the clean series independently reviewed by Agent 1; the documentation commit differs only where
the rebase retained both newer mainline context entries before this slice's entry. Final local
non-Docker gates passed; protected CI, merge, exact-main validation, and wiki publication remain
pending. Issue #448
remains open because this is only its source-recorded withholding-amount slice; exact commit and
validation evidence belongs on the issue and PR rather than in this durable methodology record.

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
  an inline rebuild, including transformed or split identities. Previously accepted suffix rows use
  the historical-rebuild context, but explicit positive DIVIDEND withholding remains part of their
  cash economics so rebuilt product and generated cash legs cannot diverge. Null/zero withholding
  and rows that predate current settlement fences retain legacy arithmetic.

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
    cost-processing output by portfolio and transaction identity and applies net-of-withholding
    current economics to it. Exact-head review then found that a later backdated booking still
    dropped withholding from a previously accepted suffix product cashflow while its generated leg
    remained net. Historical rebuild now retains explicit positive withholding, with a regression
    proving both current and suffix product cashflows equal their generated settlement legs; legacy
    fallback remains for null/zero withholding and pre-fence invalid rows.
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
