# CR-1639: Maturity Runtime Reconciliation And Calculation Lineage

## Objective

Make `PortfolioMaturitySummary:v1` a fail-closed, explainable runtime receipt over the exact booked
`HoldingsAsOf:v1` source scope without expanding the calculation beyond source-owned contractual
instrument maturity dates.

## Finding

The summary inherited holdings data quality and content identity but omitted authoritative
reconciliation, tenant, and deterministic input/calculation/output lineage. The shared runtime
metadata helper therefore emitted `reconciliation_status=UNKNOWN`; an otherwise complete holdings
book could still be labelled `SUPPORTED`. Actual HoldingsAsOf responses also left snapshot and
policy identity null and considered evidence current without reconciliation proof. The route
accepted projected holdings even though downstream opportunity evidence requires a booked receipt.

## Domain And Layer Decision

- Financial reconciliation continues to own durable portfolio-day/epoch control outcomes.
  `portfolio_common.reconciliation_quality` now owns only the cross-service durable stage/event
  vocabulary; the financial service still owns control creation and lifecycle.
- Query Service infrastructure performs one set-based read from `pipeline_stage_state` for the
  unique business-date/epoch scopes represented by selected holdings rows. It does not call the
  reconciliation service or execute one query per holding.
- Query Service application policy extracts exact scopes before ORM rows become DTOs, detects row/
  state epoch mismatches, compares control timestamps with selected source evidence, and aggregates
  the fail-closed posture.
- The existing `portfolio_common.domain.calculation_lineage` kernel remains the framework-free
  owner of canonical financial hashes. Query DTOs now share one calculation-lineage response type
  instead of retaining an allocation-specific duplicate.

## Reconciliation And Calculation Contract

Every selected snapshot or history row must map to an exact portfolio, business date, and matching
row/state epoch. Valid rows on one business date form a collective portfolio-day scope at their
maximum selected epoch because per-security epochs represent last mutation, not separate control
requirements. Position-valuation reconciliation at that target reads the latest row per security at
or below the target epoch. `COMPLETED` control evidence is complete only when its update is not older
than any selected row, instrument, or position-state evidence in that scope. Incomplete controls are partial;
failed, blocked, or replay-required controls are blocked; missing controls are unreconciled;
unrecognized or unscoped rows are unknown. The most severe exact-scope posture wins. Empty holdings
without an exact durable control remain unreconciled.

HoldingsAsOf now publishes a deterministic snapshot id, explicit `holdings-as-of-v1` policy,
reconciliation scope hash, and current evidence only when reconciliation is complete. The maturity
receipt inherits that exact source identity, binds normalized caller tenant and request correlation,
and rejects projected state.

`calculation_lineage` separates:

1. normalized inputs: portfolio, tenant, booked projection flag, horizon, and exact HoldingsAsOf
   product/as-of/snapshot/content/source-batch/policy/latest-evidence/reconciliation identity;
2. calculation: algorithm `PORTFOLIO_CONTRACTUAL_MATURITY_SUMMARY`, version `1`, integer/date
   precision, and the input hash;
3. outputs: the maturity window, counts, next maturity date, and supportability posture bound to the
   calculation hash.

Correlation remains operational evidence and is intentionally excluded from deterministic
financial hashes. Missing maturity facts and callable, putable, amortizing, structured, lockup, or
expiry classifications still degrade supportability; Core does not invent product schedules.

## Compatibility

Default booked maturity counts, inclusive horizon semantics, response product version, and
contractual-date methodology are preserved. Runtime metadata fields that were null or unknown now
carry authoritative values, and `calculation_lineage` is additive. The intentional contract
tightening is that `include_projected=true` returns HTTP 422 for this trust-certified route;
projected HoldingsAsOf remains available on the positions surface. No database migration, event,
Kafka, ingestion, valuation, cashflow, advice, suitability, or execution contract changes.

## Validation

- `78` focused exact-scope extraction, aggregation, HoldingsAsOf, and repository tests passed.
- `82` focused maturity builder/service/router/OpenAPI tests passed, covering complete, partial,
  stale, unknown, unreconciled, blocked, missing maturity facts, unsupported features, both horizon
  boundaries, rejected projected state, tenant normalization, correlation propagation, and
  deterministic identity.
- `94` allocation/reconciliation regression tests passed after promoting the reusable DTO and
  durable control vocabulary.
- The complete Query Service unit cohort passed `649/649`.
- The full position-repository PostgreSQL cohort passed `6/6`; the new proof returned only the
  requested portfolio-day/epoch control and excluded an unrelated failed scope.
- A 100,000-row scope extraction and classification proof coalesced to one scope, returned
  `COMPLETE`, and completed in `0.297686s`; the database read remains one set-based indexed query.
- Repository-native MyPy passed all `236` source files. Architecture, application, repository,
  domain, OpenAPI, API vocabulary/catalog, source-product, domain-product, RFC-0083, docs, and wiki
  guards passed.
- Signed implementation commits: `0fb28f742`, `55b9140d3`, and `568588840`.

PR #807 review then found a precedence mismatch: blocked reconciliation already produced
`supportability_status=UNAVAILABLE`, but the summary data-quality reducer fell through to the
generic reason branch and emitted `PARTIAL`. Signed fix-forward commit `276693627` now maps blocked
holdings quality or reconciliation to `data_quality_status=BLOCKED` before stale, unknown, or
partial handling. The five-state reconciliation regression now asserts data quality as well as
supportability, reason, reconciliation, and currentness; the focused maturity suite passes `14/14`
and full MyPy passes all `237` source files.

A later PR review found the shared `HoldingsAsOf:v1` content/source-batch identity included returned
positions and data quality but omitted the reconciliation status and exact reconciliation scope
hash. A trust transition could therefore retain the same source receipt. The identity payload now
binds both fields, so `COMPLETE` to `BLOCKED` transitions and exact-scope corrections produce a new
content hash, source digest, source-batch fingerprint, and snapshot id. The bounded same-pattern
scan confirmed the maturity receipt inherits this corrected HoldingsAsOf identity and
`PortfolioStateSnapshot:v1` already hashes its exact control evidence independently.

The next PR review identified a shared trust-classification gap in both upstream products: current
source rows could still emit `data_quality_status=COMPLETE` while exact reconciliation was missing,
running, failed, or stale. One reusable reducer now combines source quality with reconciliation
using fail-closed precedence: `BLOCKED`, `STALE`, `UNKNOWN` for unknown/unreconciled evidence,
`PARTIAL`, then `COMPLETE` only when both inputs are complete. `PortfolioStateSnapshot:v1`,
`HoldingsAsOf:v1`, and the maturity receipt all use that policy, removing the maturity-local
duplicate. Focused reconciliation, snapshot, holdings, and maturity validation passes `136` tests;
strict MyPy passes all `237` sources.

## Documentation And Wiki Decision

The source-data-product declaration, methodology, RFC-0083 catalog, repository context, this
review, review ledger, and existing API Surface wiki change because producer/runtime and consumer
truth changed. No new generic lineage guide or duplicate documentation family is added.
The review fix requires no additional wiki change: the existing API Surface already states that
failed/replay-required reconciliation fails closed, while the exact field precedence belongs in
the implementation methodology, API model, tests, and this review record.
The shared upstream quality correction likewise requires no additional wiki page or OpenAPI shape
change. Existing Mesh Data Products and API Surface wiki truth already requires fail-closed exact
reconciliation; the HoldingsAsOf methodology and executable contracts now make the field-level
reduction explicit.

## Downstream Consumer-Path Fix-Forward

PR #807 merged the producer contract to exact main `6e4dbf2a6bc17adf4b95937b1d2b8338216f976e`.
A live Lotus Idea request then exposed an HTTP binding defect: FastAPI did not coerce the query
string `include_projected=false` into the route's `Literal[False]`, so the governed explicit request
returned 422 even though omission returned a complete, current, supported receipt. The route now
parses the parameter as a boolean, rejects `true` before service execution, and retains OpenAPI
`const: false` through explicit schema metadata. Focused route and OpenAPI validation passes 48
tests with warnings treated as errors. The same-pattern production scan found no other
`Literal[False]` HTTP parameter.

This corrects transport binding only. Booked-only maturity methodology, response shape, OpenAPI
const posture, reconciliation, identity, lineage, and downstream authority boundaries are
unchanged. Existing API Surface wiki and methodology truth therefore require no further update.
Issue #792 remains open until Lotus Idea's real runtime artifact qualifies against this exact Core
fix and the fix reaches exact main.

## Canonical Mixed-Epoch Correction

Canonical retained-state proof exposed snapshots at epochs `0`, `1`, and `3` for one business date
with one completed portfolio control at epoch `3`. The original reader incorrectly required three
controls, while the original position-valuation reconciliation at epoch `3` examined only the
single row mutated at epoch `3`; accepting either behavior would misstate the certified book.

The shared framework-independent policy now produces one order-independent collective scope at the
maximum valid row epoch and retains the latest evidence timestamp across every included security.
Query Service and QCP keep their source adapters. Financial reconciliation now selects one latest
snapshot per normalized security at the exact business date with `epoch <= target`, excluding a
later epoch and any superseded lower row. Mismatched or invalid row/state epochs still fail closed.
This changes no HTTP, OpenAPI, database, event, or Kafka shape; mixed-epoch scope/content hashes
intentionally change. Focused warning-strict proof passes `33` unit tests and one isolated
PostgreSQL selection scenario. Fresh canonical controls and downstream proof remain required; an
older control created under the superseded calculation is not valid certification evidence.

Fresh branch-qualified proof at signed SHA `a3d8dee29859f5ddd3749590039642b81e17fda8`
used canonical book `PB_SG_GLOBAL_BAL_001` on `2026-04-10`, where 11 security rows span epochs
`0`, `1`, and `3`. Correlation `CTL:a3d8dee:PB_SG_GLOBAL_BAL_001:2026-04-10:3` produced three new
completed runs. Position valuation examined all 11 authoritative rows with zero findings, compared
with one examined row in the pre-fix control. Completion and controls-evaluated outbox rows were
processed with zero retries. HoldingsAsOf and PortfolioMaturitySummary both reported complete,
current, reconciled evidence; the maturity receipt was `SUPPORTED` with all three calculation-
lineage hashes populated.

The real Lotus Idea adapter retrieved that receipt successfully but exposed a consumer-owned empty-
window decision defect: a supported zero-count/null-next-date receipt was classified as
`blocked/missing_source` instead of `not_eligible`. `lotus-idea#482` was reopened with the exact live
evidence and root cause. Core issue #792 therefore remains in progress until the consumer fix-forward
passes and the producer change completes PR, exact-main, wiki-publication, and closure gates.
