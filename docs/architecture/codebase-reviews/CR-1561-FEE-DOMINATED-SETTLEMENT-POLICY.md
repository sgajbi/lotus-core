# CR-1561: Fee-Dominated Settlement Policy

Date: 2026-07-14
Issues: #752, contributes to #719 and #731; follow-ups #448 and #754
Status: Review fix-forward locally validated; refreshed PR proof pending

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
- Classified persisted-event idempotency before validating settlement economics so historical
  physical and semantic duplicates remain harmless acknowledgements. Newly claimed and repair
  deliveries are rejected before cost, position, cashflow, or commit; the uncommitted claim rolls
  back with the unit of work. Direct adapter paths preserve the same application rejection.
- Added an explicit cashflow calculation context for position-history rebuild rows. Current
  bookings always use the strict policy, while source-owned historical rebuild rows reproduce their
  pre-policy economics so a valid backdated correction cannot roll back or dead-letter solely
  because previously accepted history predates this policy. The application derives this context
  only from rebuilt transaction identities; repair intent is not used as a policy bypass.
- Preserved bounded reason codes through terminal consumer handling without leaking raw payloads,
  credentials, or infrastructure detail.
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
- FX has two currencies and no governed fee-currency/leg ownership; #754 owns that decision. This
  slice preserves existing zero-fee FX behavior without claiming the same policy applies.
- ADJUSTMENT uses positive magnitude plus explicit movement direction; its normalization is a
  representation rule, not repair of invalid net proceeds.
- Corporate-action cash already rejects fee above gross; its explicit zero boundary remains a
  separate family policy.

No behavior was broadened for those families in this slice.

The current DIVIDEND path uses booked gross amount as available proceeds, while the canonical RFC
requires net-dividend settlement after withholding and other deductions. #448 owns that existing
methodology/runtime gap; this slice preserves valid-input behavior and does not claim its closure.

## Validation

- 13 settlement-policy unit cases and 26 generated-leg/policy cases passed.
- 43 cashflow/domain and 30 canonical-validation cases passed.
- 24 application/adapter and 9 consumer cases passed.
- Seven PostgreSQL rejection/replay cases passed in 110.10 seconds.
- Three PostgreSQL corrected-redelivery cases passed in 83.18 seconds.
- Three PostgreSQL positive generated-settlement reconciliation cases passed in 86.19 seconds.
- Review fix-forward proof passed 18 application cases plus two PostgreSQL historical physical and
  semantic duplicate cases; neither duplicate created financial outbox or idempotency state.
- The second review fix-forward passed 116 focused cashflow/application/adapter cases and the
  complete 72-case PostgreSQL transaction-processing contract in 253.72 seconds. Domain vectors
  prove pre-policy SELL, DIVIDEND, and INTEREST economics only under historical rebuild context;
  application and adapter tests prove explicit context routing through every layer.
- The third review fix-forward aligned the shared transaction RFC with the implemented
  idempotency-first, pre-financial-work rejection boundary; a same-pattern search found no other
  settlement document that claimed rejection precedes the combined unit of work.
- Focused Ruff, RFC status ledger, and diff checks passed.
- Governed SELL, DIVIDEND, and INTEREST contracts passed 152, 303, and 330 cases.
- The complete PostgreSQL transaction-processing contract passed 72 cases in 253.72 seconds after
  both review fixes.
- Final `make ci-local` passed 4,414 zero-warning unit tests, 10 unit-DB tests, and 136
  integration-lite tests at 97.79% aggregate and 91.24% branch coverage.
- Configured MyPy, architecture, application error taxonomy, security-control coverage, event,
  image-provenance, OpenAPI, API-vocabulary, documentation, wiki, Ruff, and diff gates passed.
- The initial PR gate passed all 40 checks. Review fix-forward PR checks and exact-main proof remain
  pending.

## Documentation Decision

Transaction RFCs, ingestion API diagnostics, repository context, and the existing
transaction/cashflow wiki pages change because calculation, runtime rejection, and support truth
changed. README, OpenAPI schema, API inventory, database catalog, migrations, image metadata,
runtime topology, central platform context, AGENTS guidance, and platform skills do not change
because their owned contracts and reusable workflow did not.
