# CR-1560: INTEREST Settlement Economics

Date: 2026-07-13
Issues: #750, contributes to #719 and #731
Status: Locally validated; PR proof pending

## Objective

Make settlement cash invariant to whether an economically equivalent INTEREST transaction supplies
`net_interest_amount`, while preserving explicit income, fee, tax, direction, and reconciliation
evidence.

## Finding

Three domain paths owned overlapping arithmetic:

- validation reconciled `net_interest_amount` to gross interest less withholding and other
  deductions, excluding transaction fees;
- generated cash legs used an explicit net amount unchanged but deducted the fee from a derived
  net amount;
- cashflow materialization repeated the same conditional formula.

The result depended on source payload shape. A conforming explicit net bypassed the fee, and the
existing direction-neutral subtraction also made an expense fee reduce the cash payment.

## Methodology Decision

`net_interest_amount` is the interest amount after withholding tax and other interest deductions
but before separately reported transaction fees:

```text
net_interest = gross_interest - withholding_tax - other_interest_deductions
income_settlement_cash = net_interest - transaction_fee
expense_settlement_cash = net_interest + transaction_fee
```

Settlement cash is a positive magnitude at the economics boundary. The cashflow policy applies the
inflow or outflow sign from `interest_direction`.

## Implementation

- Added immutable `InterestSettlementEconomics` and
  `calculate_interest_settlement_economics(...)` under the service-owned transaction settlement
  domain.
- Routed INTEREST reconciliation, generated cash-leg construction, and cashflow materialization
  through the policy and removed their duplicate formulas.
- Preserved the exact `INTEREST_015_NET_RECONCILIATION_MISMATCH` reason code and field mapping.
- Clarified ingestion and query OpenAPI descriptions without changing field shape.
- Added independent versioned JSON vectors and a Decimal-only reference evaluator with no
  production imports.
- Added a PostgreSQL lifecycle case proving equivalent explicit and derived transactions persist
  equal cashflow amounts while preserving source net-interest evidence and zero position effect.
- Added the new proof to the repository-native `transaction-interest-contract` manifest.

## Compatibility

This is an intentional calculation correction for fee-bearing INTEREST transactions:

- explicit pre-fee net income now deducts the transaction fee exactly once;
- expense settlement now adds the transaction fee to the payment magnitude;
- zero-fee behavior and pre-fee net-interest reconciliation are unchanged.

No route, field name, event schema/version, topic, database column/table, migration, runtime
topology, reason code, or downstream response shape changes. Consumers that treated
`net_interest_amount` as final settlement cash must use the linked cashflow amount instead.

## Validation

- Pure settlement, validation, generated-leg, cashflow, methodology, and golden-vector cohorts
  passed.
- PostgreSQL combined processing proof passed for explicit and derived source shapes.
- Independent golden vectors cover income and expense explicit/derived fee-bearing cases; focused
  policy and validation tests cover invalid direction and reconciliation rejection.
- The governed INTEREST contract passed 314 cases.
- Repository-native local CI passed 4,355 unit tests with zero warnings, 10 unit-DB tests, and 136
  integration-lite tests at 97.79% aggregate and 91.24% branch coverage.
- Configured MyPy, architecture, domain-layer, in-process boundary, image provenance, OpenAPI,
  API-vocabulary, documentation, wiki, Ruff, and diff gates passed.
- PR checks and exact-main proof remain pending.

## Same-Pattern Follow-up

The review also found that fee-dominated SELL, DIVIDEND, or INTEREST income can produce a
non-positive intermediate magnitude that absolute-value signing may mask. Issue #752 owns the
required cross-family product and ledger decision; it is intentionally not folded into this
single-family correction.

## Documentation Decision

The canonical INTEREST RFC, conformance report, performance-component methodology, OpenAPI field
descriptions, repository context, review ledger, and existing transaction/cashflow wiki pages change
because calculation truth changed. The repeatable source-shape and fee-direction lesson is promoted
to the platform-owned transaction skill in lotus-platform PR #521. README, API route inventory,
database catalog, migrations, supported-feature claims, central context, and skill routing do not
change: entrypoints, shapes, storage, public capability, and task routing remain unchanged.
