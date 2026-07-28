# CR-1659: Owner-Specific Financial Numeric Boundaries

## Scope

This review tracks bounded GitHub issue #829 owner-specific numeric work across generic simulation,
position-history accumulation, durable cashflow amounts, accrued-income calculation, position
valuation, and the shared calculated-output arithmetic and lineage contracts. It does not claim
closure of persisted lineage exposure or the complete producer-policy inventory.

## Findings

- Generic simulation quantity, price, and amount accepted lossy JSON floating-point values and
  values that could not fit the existing `NUMERIC(18,10)` persistence boundary.
- Position-history and cashflow calculations inherited the process-global `Decimal` context and
  could produce scale-amplified values that relied on the final exact bind to reject them.
- The generator-based calculated-output context manager attempted to mutate exception traceback
  state during unwinding, which is incompatible with frozen domain exceptions.
- Cashflow events did not independently enforce the amount storage contract.
- Accrued-income and position-valuation calculations used explicit high-precision arithmetic but
  returned scale-amplified outputs without executing their ledger-output policies.
- Calculation lineage could bind algorithm and intermediate precision but could not distinguish a
  numeric-output policy revision from an unchanged calculation method.

## Resolution

- Moved the proven exact Pydantic financial numeric types into `portfolio_common` after a second
  service consumer existed, migrated all existing ingestion owners, and removed the duplicate
  ingestion-local module.
- Added domain-owned simulation validation at both request and application boundaries. Fractional
  values must be lexical decimals; lossless integers remain accepted.
- Added named `position-history-ledger-output@1.0.0` and
  `cashflow-ledger-output@1.0.0` calculated-output policies. Both run intermediate arithmetic in a
  deterministic high-precision local context and normalize once at the durable boundary.
- Made the shared arithmetic-context API return the native decimal context manager so frozen
  domain exceptions retain their identity.
- Applied exact `NUMERIC(18,10)` validation to durable cashflow events.
- Added complete numeric-output policy identity to calculation lineage without changing hashes for
  calculations that do not opt into the new evidence.
- Added named `accrued-income-ledger-output@1.0.0` ownership and activated the existing
  `position-valuation-ledger-output@1.0.0` policy.
- Accrued-income and position-valuation calculations now use deterministic 64-digit working
  precision, normalize once to `NUMERIC(18,10)`, fail before persistence on magnitude overflow,
  and bind policy name/version/shape/rounding into calculation lineage.
- Position valuation normalizes clean value and accrued income before deriving the durable total,
  so the visible component sum remains exactly equal to total market value after rounding.

No database schema, migration, topic identity, or runtime topology changed. Exactly representable
inputs and serialized Decimal values remain unchanged.

## Evidence

- Signed commits `5fa97db88`, `c1132d7cf`, `f67c82e38`, `ba34863b3`, and `0a63edafe`.
- 174 warning-strict cashflow, position, event, and arithmetic-context tests passed.
- Simulation request, application-bypass, router, and OpenAPI tests cover float, excess-scale,
  magnitude, non-finite, nonpositive-price, and exact-boundary behavior.
- Repository-native type checking passed across 240 source files.
- OpenAPI quality, API vocabulary parity, financial-numeric persistence, domain-layer, Ruff,
  formatting, and diff-hygiene gates passed.
- Signed commits `0cfbb2c57`, `fb83c0819`, and `8454cbaca` continue the review.
- 87 warning-strict lineage, precision, accrued-income, and position-valuation tests passed,
  including policy-version hash changes, ambient-context independence, half-even normalization,
  component reconciliation, and pre-persistence overflow rejection.
- Repository-native MyPy passed across 240 source files.

## Compatibility and remaining work

The simulation contract intentionally rejects values that could previously be changed or rejected
only after acceptance. Gateway #511 is exact-main complete. Accrued-income and position-valuation
lineage hashes intentionally change because numeric policy is now calculation identity. Issue #829
remains open for complete producer-policy inventory reconciliation and persisted/exposed
calculation-policy lineage compatibility.

## Documentation decision

Repository context and this existing review record carry the new implementation truth without
adding a duplicate document. No API/OpenAPI shape, operator command, database migration, or
wiki-authored workflow changed, so no wiki source update is required.
