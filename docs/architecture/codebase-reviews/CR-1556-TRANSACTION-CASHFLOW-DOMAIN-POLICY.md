# CR-1556: Transaction Cashflow Domain Policy

Date: 2026-07-13
Issue: #719
Status: Locally validated; PR proof pending

## Objective

Move canonical cashflow economics out of infrastructure while preserving the deployed combined
transaction-processing behavior and downstream contracts.

## Finding

`cashflow_calculation.py` combined amount, fee, sign, timing, transfer, income, synthetic-flow,
corporate-action, and flow-level policy with `TransactionEvent`, SQLAlchemy `Cashflow` construction,
Prometheus metrics, and logging. The unified runtime therefore owned cashflow execution but not a
clean domain boundary. Its canonical adapter also converted `BookedTransaction` to an event DTO and
back before calculation.

## Implementation

- Added immutable `CashflowRule` and `CalculatedCashflow` domain records.
- Added a deterministic `calculate_transaction_cashflow` policy over `BookedTransaction`.
- Preserved trade fee, income deduction/direction, settlement/payment date, transfer sign,
  synthetic market-value flow, corporate-action duplicate-flow, classification, timing, lineage,
  and epoch semantics.
- Reduced the infrastructure calculator from 311 to 109 lines and retained its existing event/ORM
  entry point as a compatibility facade.
- Passed the existing booked transaction through the unified staging path, avoiding a DTO round
  trip on the canonical path.
- Made the production repository accept immutable calculated results and construct SQLAlchemy rows
  at the persistence boundary.
- Extended the global in-process boundary guard so domain packages cannot import
  `portfolio_common.monitoring`.

## Compatibility Decision

No API route, OpenAPI schema, event schema/topic, database schema, migration, transaction ordering,
amount/sign/timing rule, persisted field, rule-cache behavior, idempotency key, epoch fence,
outbox behavior, deployment topology, or downstream response changed. Existing
`CashflowCalculator` imports remain available during caller migration.

README, API inventory, supported-feature inventory, central platform context, and central skills
did not change because the public surface and platform-wide operating contract are unchanged.

## Validation

- Pure domain policy: 5 focused cases passed.
- Legacy cashflow calculator compatibility: 59 cases passed.
- Interest, dividend, cross-product, and portfolio-flow transaction specifications: 34 cases
  passed.
- Cashflow adapter, staging, calculation, repository, transaction specification, and portfolio-flow
  cohorts passed 120 cases in the final focused cross-module run.
- Concrete PostgreSQL combined BUY/SELL lifecycle: 2 cases passed.
- Complete PostgreSQL transaction-processing contract: 52 cases passed.
- `make ci-local` passed dependency integrity, Ruff, zero-warning, MyPy, architecture, OpenAPI,
  API-vocabulary, unit DB, integration-lite, and coverage gates: 4,338 unit, 10 DB, and 135
  integration-lite cases passed; aggregate measured coverage was 97.79% with 91.24% branch
  coverage.
- Domain-layer, in-process boundary, documentation, and diff checks passed. The pre-merge wiki
  check reported only `Cashflow-Calculator.md`, the expected authored source change that must not
  be published before merge.

PR CI, exact-branch validation, and post-merge exact-main proof remain required before this bounded
slice is complete. Issue #719 remains open for the broader cost/position workflow, port, replay,
simulation, performance, and legacy-retirement program.

## Same-Pattern Decision

The domain guard now prevents ORM, event DTO, infrastructure-layer, and monitoring dependencies
from returning anywhere under service domain packages. Four existing QCP application modules still
import monitoring directly; that is application observability-port work outside this transaction
cashflow slice and remains under the broader application decomposition backlog rather than being
silently folded into #719.

The audit also found that the curated `make lint` path list did not include transaction-processing
production code. The immediate changed files were checked and formatted directly; issue #745 now
tracks repository-wide changed-file lint and format enforcement so this omission cannot recur
silently.
