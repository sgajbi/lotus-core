# CR-1659: Owner-Specific Financial Numeric Boundaries

## Scope

This bounded continuation of GitHub issue #829 covers generic simulation commands, position-history
accumulation, durable cashflow amounts, and the shared calculated-output arithmetic context. It
does not claim closure of accrued-income ownership, calculation-lineage cutover, or downstream
Gateway compatibility tracked by `sgajbi/lotus-gateway#511`.

## Findings

- Generic simulation quantity, price, and amount accepted lossy JSON floating-point values and
  values that could not fit the existing `NUMERIC(18,10)` persistence boundary.
- Position-history and cashflow calculations inherited the process-global `Decimal` context and
  could produce scale-amplified values that relied on the final exact bind to reject them.
- The generator-based calculated-output context manager attempted to mutate exception traceback
  state during unwinding, which is incompatible with frozen domain exceptions.
- Cashflow events did not independently enforce the amount storage contract.

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

## Compatibility and remaining work

The simulation contract intentionally rejects values that could previously be changed or rejected
only after acceptance. Gateway #511 must forward lexical decimal values before this contract is
downstream-safe. Issue #829 remains open for that proof, accrued-income ownership, the complete
producer-policy inventory, and persisted calculation-policy lineage compatibility.

## Documentation decision

OpenAPI and this review ledger are the durable truth changed by the slice. No operator command,
business methodology, database migration, or wiki-authored flow changed, so no wiki source update
is required.
