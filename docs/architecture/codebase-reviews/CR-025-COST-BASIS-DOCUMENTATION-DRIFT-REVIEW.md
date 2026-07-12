# CR-025 Cost-Basis Documentation Drift Review

## Scope

Review current-state transaction specification documents for cost-basis
terminology drift after the canonical `FIFO` / `AVCO` policy cleanup.

## Finding

Several transaction specs still documented unsupported policy names:

- `LIFO`
- `AVERAGE_COST`
- `SPECIFIC_ID`
- `SPECIFIC_LOT`

That was no longer accurate for current lotus-core behavior. The live code now
supports only canonical:

- `FIFO`
- `AVCO`

Leaving the broader list in current-state specs made the documentation less
trustworthy than the implementation.

## Action Taken

1. Updated the SELL transaction spec decision table to use `AVCO`.
2. Updated the redemption family spec to state the currently supported policy
   set as `FIFO | AVCO`.
3. Updated the FX transaction spec to state the currently supported policy set
   as `FIFO | AVCO`.

## Result

The transaction specs no longer advertise unsupported policy values as if they
were active lotus-core behavior.

## Evidence

- `docs/rfc-transaction-specs/transactions/SELL/RFC-SELL-01.md`
- `docs/rfc-transaction-specs/transactions/misc/RFC-REDEMPTION-01 Canonical Fixed Income Redemption Family Specification.md`
- `docs/rfc-transaction-specs/transactions/FX/RFC-FX-01 Canonical FX Transaction Specification.md`
