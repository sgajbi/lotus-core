# CR-1559: Ordinary Transaction Domain Ownership

Date: 2026-07-13
Issues: #719, #466
Status: Locally validated; PR proof pending

## Objective

Make the unified transaction-processing service the single owner of ordinary transaction booking,
validation, and settlement policy while preserving existing external and downstream contracts.

## Finding

The runtime owner had an immutable `BookedTransaction`, but BUY, SELL, DIVIDEND, and INTEREST
metadata enrichment, validation, cash-entry policy, generated settlement-leg economics, and
upstream pairing still lived under `portfolio_common.transaction_domain`. Those shared modules
depended on Pydantic `TransactionEvent` or duplicate per-type Pydantic models. The split created two
domain representations, repeated near-identical policy code, framework leakage, extra DTO mapping,
and an ambiguous extension point for agents and maintainers.

## Implementation

- Added cohesive `app/domain/transaction/validation` and `app/domain/transaction/settlement`
  packages plus one booking-metadata policy over immutable `BookedTransaction`.
- Preserved all stable validation reason-code values and ordinary BUY, SELL, DIVIDEND, and INTEREST
  metadata, cash-entry, generated-leg, interest-netting, and pairing behavior.
- Routed cost and cashflow infrastructure through the service-owned policies, mapped each cashflow
  event once, and replaced in-place event mutation with immutable domain replacement.
- Added an infrastructure mapper that applies domain fields without losing governed event-envelope
  metadata.
- Removed 20 obsolete shared source modules and 12 duplicate ordinary-policy test files. Retained
  the valid FX model tests under explicit FX filenames.
- Repointed governed transaction suites and critical-path coverage to the service-owned tests and
  added a structure guard that blocks reintroduction of every retired module.

## Architecture And Compatibility

The ordinary flow is delivery/event DTO -> infrastructure mapper -> immutable booked transaction ->
domain booking/validation/settlement policy -> infrastructure workflow/repository -> database and
outbox. Corporate-action, FX, and effective-processing compatibility remain in the shared package
because this slice did not establish evidence for moving those cross-cutting contracts.

There is no public API, OpenAPI, event field, schema version, topic, database table, migration,
calculation formula, transaction timing, runtime topology, or downstream response change. Generated
product/cash event ordering and linkage are preserved. The internal workflow no longer mutates the
input Pydantic event in place; it emits the same enriched product event followed by the same cash
leg through an immutable mapping path.

## Validation

- Service transaction, shared-library, and remaining FX cohort: `803 passed`.
- Full repository-native local CI passed: `4,330` unit tests with zero warnings, `10` database
  tests, and `135` integration-lite tests.
- Coverage validation passed at `97.79%` aggregate coverage and `91.24%` branch coverage; the
  critical-path coverage guard passed with the service-owned transaction test paths.
- Focused booking, settlement, workflow, validation, mapper, and registry cohorts passed throughout
  the slice, including 39 settlement/workflow cases, 26 cashflow-policy cases, and 68 replacement
  transaction/FX cases.
- Ruff lint/format and focused MyPy passed for the new domain and touched workflows. A broad direct
  MyPy invocation exposed five pre-existing CA/effective-processing findings outside this slice;
  the repository-native configured typecheck remains the aggregate authority.
- BUY, SELL, DIVIDEND, INTEREST, and combined transaction-processing aggregate suites passed `979`
  cases.

## Documentation Decision

Repository context, current RFC/conformance evidence, codebase review ledger, and architecture,
cost, and cashflow wiki source changed because ownership truth changed. README and supported-feature
claims did not change because no public capability changed. No platform skill update is required:
existing backend delivery, codebase review, and repository-context governance already mandate
framework-neutral domain models, evidence-led dead-code retirement, and durable prevention guards.

## Remaining Work

Continue #719 with the remaining cost/cashflow source ownership and layered application/port
boundaries. Continue #466 for evidence-led separation of other shared-library responsibilities.
Keep CA and FX compatibility in place until their production consumers, contracts, and target owner
are independently mapped and validated.
