# CR-1561: Fee-Dominated Settlement Policy

Date: 2026-07-14
Issues: #752, contributes to #719 and #731
Status: Locally validated; full PR proof pending

## Objective

Prevent ordinary transaction fees from converting invalid zero or negative proceeds into an
apparent cash inflow, while keeping cost, cashflow, position, replay, and failure behavior atomic.

## Finding

SELL, DIVIDEND, and INTEREST income paths resolved fees in more than one place. Cashflow signing
could apply an absolute value after subtraction, so a fee-equal or fee-dominated transaction could
look like a valid zero or positive inflow. Generated cash legs and product cashflows also lacked one
cross-family policy result and one stable application rejection mapping.

## Domain Decision

One immutable settlement policy owns fee precedence, signed amount, and direction:

```text
buy = -(gross amount + resolved fee)
sell = gross proceeds - resolved fee
dividend = gross dividend - resolved fee
interest income = pre-fee net interest - resolved fee
interest expense = -(pre-fee net interest + resolved fee)
```

Component fee fields take precedence over aggregate `trade_fee` when present. SELL, DIVIDEND, and
INTEREST income must remain strictly positive before an inflow direction is applied. Zero or
negative proceeds are non-retryable hard rejections with stable family codes.

## Implementation

- Added the service-owned `SettlementCashMovement` policy and stable reason-code vocabulary.
- Routed generated settlement legs and cashflow materialization through the signed policy result.
- Rejected invalid ordinary settlement before opening the combined transaction-processing unit of
  work; direct adapter paths preserve the same application rejection.
- Preserved bounded reason codes through terminal consumer handling without leaking exception or
  payload detail.
- Added independent Decimal golden vectors plus pure domain, validator, adapter, consumer,
  persistence, replay, rollback, idempotency-recovery, and generated-leg reconciliation tests.
- Kept the regression in the governed SELL, DIVIDEND, INTEREST, and complete transaction-processing
  contract manifests.

## Compatibility

This is an intentional correctness change: fee-equal and fee-dominated SELL, DIVIDEND, and INTEREST
income are rejected instead of materializing misleading settlement cash. Valid and zero-fee
transactions retain their existing amounts and direction. No route, OpenAPI shape, event schema or
version, topic, database table or column, migration, image, runtime topology, or downstream response
shape changed.

## Same-Pattern Audit

- BUY and FEE use additive outflow fees and do not subtract fees from proceeds.
- FX uses independently positive buy/sell cash legs plus explicit leg roles.
- ADJUSTMENT uses positive magnitude plus explicit movement direction; its normalization is a
  representation rule, not repair of invalid net proceeds.
- Corporate-action cash already rejects fee above gross; its explicit zero boundary remains a
  separate family policy.

No behavior was broadened for those families in this slice.

## Validation

- 13 settlement-policy unit cases and 26 generated-leg/policy cases passed.
- 43 cashflow/domain and 30 canonical-validation cases passed.
- 24 application/adapter and 9 consumer cases passed.
- Seven PostgreSQL rejection/replay cases passed in 110.10 seconds.
- Three PostgreSQL corrected-redelivery cases passed in 83.18 seconds.
- Three PostgreSQL positive generated-settlement reconciliation cases passed in 86.19 seconds.
- Focused Ruff, RFC status ledger, and diff checks passed.
- Full repository and PR gates remain pending.

## Documentation Decision

Transaction RFCs, repository context, and the existing transaction/cashflow wiki pages change
because calculation and runtime rejection truth changed. README, OpenAPI, API inventory, database
catalog, migrations, image metadata, runtime topology, central platform context, AGENTS guidance,
and platform skills do not change because their owned contracts and reusable workflow did not.
