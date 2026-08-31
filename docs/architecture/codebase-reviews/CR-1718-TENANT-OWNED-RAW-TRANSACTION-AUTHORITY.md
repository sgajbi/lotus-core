# CR-1718: Tenant-Owned Raw Transaction Authority

## Scope

Issue #798 S1 review found that portfolio-bundle admission and raw transaction persistence did not
share one durable tenant authority. A concurrent tenant could win ownership of the same new
`portfolio_id` after admission but before asynchronous consumption, allowing the original
tenantless transaction event to be booked against the wrong portfolio.

The same-pattern review also found two QCP request bodies whose caller-supplied `tenant_id` was not
bound to the admitted HTTP tenant before service execution.

## Hardened contract

- All transaction producers inject the admitted tenant into the event payload, including single,
  batch, bundle, and bulk-upload flows.
- `transactions.raw.received` uses `RawTransactionEvent`, which requires normalized tenant authority.
- Persistence resolves portfolio availability by `(tenant_id, portfolio_id)` before staging a raw
  transaction. Missing and foreign ownership follow the same fail-closed path.
- Tenant authority is transport lineage, not a duplicated transaction-table ownership column; the
  authoritative portfolio remains the system-of-record owner.
- Canonical transaction replay joins the portfolio and republishes its tenant authority.
- Instrument eligibility and external FX forward-curve requests reject body/header tenant mismatch
  before source reads or response construction.

## Evidence

- Raw-event tests reject absent tenant authority and normalize admitted identifiers.
- Producer tests prove the emitted payload carries the admitted tenant.
- PostgreSQL repository evidence proves the same portfolio is unavailable under a foreign tenant.
- Replay tests prove tenant authority survives deterministic republishing.
- QCP router tests prove mismatch rejection occurs before service access.

No database migration is required because portfolio ownership remains canonical and transaction
tenant authority is verified before persistence rather than duplicated as mutable row state.
