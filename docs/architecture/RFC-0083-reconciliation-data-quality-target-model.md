# RFC-0083 Reconciliation And Data-Quality Target Model

This document is the RFC-0083 Slice 5 target model for reconciliation evidence, break handling, and
data-quality coverage in `lotus-core`.

It defines the vocabulary and supportability fields now used by the additive reconciliation and
coverage runtime evidence contracts.

## Target Principle

Reconciliation and data-quality state are source-truth controls, not operational decorations.

Downstream consumers must be able to determine whether portfolio, transaction, cash, position,
market-data, benchmark, and analytics-input products are complete, partial, stale, unreconciled,
blocked, or unknown without reading logs or private database tables.

## Current Implementation Baseline

Current useful building blocks:

1. `financial_reconciliation_service` executes transaction-to-cashflow, position valuation, and
   timeseries integrity controls.
2. `financial_reconciliation_runs` records run status, requested-by, correlation, dedupe,
   aggregation revision, tolerance, summary, failure, start, and completion metadata. Automatic
   runs reconcile each durable aggregation revision exactly once; manual and legacy runs may have
   no revision.
3. `financial_reconciliation_findings` records finding type, severity, portfolio, security,
   transaction, business date, epoch, expected value, observed value, detail, and creation timestamp.
4. `query_control_plane_service` exposes support routes for reconciliation runs and findings.
5. `query_service` support DTOs already expose `is_blocking`, operational state, correlation,
   requested-by, dedupe key, and top blocking finding fields for reconciliation support views.
6. readiness and coverage routes already expose useful foundations for data-quality coverage.

Current runtime posture:

1. QCP reconciliation run/finding routes publish `ReconciliationEvidenceBundle:v1` identities,
   normalized status, tolerance, severity counts, owner/action, age, and fail-closed publication gates,
2. `financial_reconciliation_findings` persists owner, resolution state, terminal actor/timestamp,
   finite tolerance/delta, and repair recommendation,
3. coverage routes publish deterministic `DataQualityCoverageReport:v1` identities, required/observed
   and issue counts, evidence references, age/threshold, and publication gates,
4. run-list gates block when a paged response cannot prove the complete filtered evidence window,
5. no operator-facing resolution-transition command is claimed by this evidence-publication slice.

## Target Status Vocabulary

The executable helper is:

1. `src/libs/portfolio-common/portfolio_common/reconciliation_quality.py`
2. `tests/unit/libs/portfolio-common/test_reconciliation_quality.py`

Target statuses:

| Status | Meaning |
| --- | --- |
| `COMPLETE` | Reconciliation or quality coverage is complete and no open issue affects the product |
| `PARTIAL` | Some coverage exists but warnings, running controls, or incomplete inputs remain |
| `STALE` | Evidence exists but is older than the product or supportability freshness threshold |
| `UNRECONCILED` | Required reconciliation or coverage has not run or has no observed data |
| `BREAK_OPEN` | A non-blocking break remains open and must be visible to consumers/operators |
| `BLOCKED` | A blocking run, finding, or data-quality issue prevents safe downstream use |
| `UNKNOWN` | Inputs are insufficient to classify the state truthfully |

Runtime and source-data products may keep existing lifecycle statuses, but they must expose or map to
this target status vocabulary when downstream consumers need safety decisions.

## Reconciliation Evidence Bundle

Target `ReconciliationEvidenceBundle` fields:

1. `reconciliation_evidence_id`,
2. `portfolio_id`,
3. source-data product name and version,
4. business/as-of scope,
5. epoch or snapshot identity when applicable,
6. reconciliation status from the target vocabulary,
7. latest run id, run status, started/completed timestamps, requested by, correlation id, dedupe key,
8. run summary: examined count, finding count, error count, warning count,
9. blocking flag and publish/release decision,
10. top blocking finding reference,
11. open break count by severity,
12. stale threshold and evidence age,
13. generated-at timestamp.

## Break Model

Target break fields:

1. `finding_id`,
2. `finding_type`,
3. severity,
4. owner,
5. resolution state,
6. age,
7. tolerance and observed delta when value-based,
8. portfolio/security/transaction/date/epoch scope,
9. expected value and observed value,
10. blocking flag,
11. repair recommendation.

Break severity vocabulary:

| Severity | Target treatment |
| --- | --- |
| `BLOCKER` | Blocking |
| `CRITICAL` | Blocking |
| `ERROR` | Blocking |
| `WARNING` | Non-blocking open break |
| `INFO` | Non-blocking open break |

Resolution states:

1. `OPEN`,
2. `IN_PROGRESS`,
3. `RESOLVED`,
4. `WAIVED`,
5. `SUPPRESSED`.

Resolved, waived, and suppressed breaks must not block publication, but they must remain auditable
where source-data product safety depends on prior exceptions.

## Data-Quality Coverage Report

Target `DataQualityCoverageReport` fields:

1. `coverage_report_id`,
2. source-data product name and version,
3. portfolio/security/reference/market scope,
4. required count,
5. observed count,
6. missing count,
7. stale count,
8. blocking issue count,
9. warning issue count,
10. freshness threshold and evidence age,
11. status from the target vocabulary,
12. generated-at timestamp,
13. contributing ingestion, reconciliation, and source batch evidence ids where available.

Coverage classification:

1. blocking issues produce `BLOCKED`,
2. stale evidence produces `STALE`,
3. zero observed data for a required scope produces `UNRECONCILED`,
4. partial observed data or warnings produce `PARTIAL`,
5. full observed data with no issues produces `COMPLETE`,
6. insufficient scope produces `UNKNOWN`.

## Source-Data Product Supportability Fields

Every source-data product that can affect safety must expose or reference:

1. reconciliation status,
2. data-quality status,
3. latest evidence timestamp,
4. blocking flag,
5. evidence ids or run ids,
6. freshness/completeness summary,
7. restatement version or snapshot identity where applicable.

## Boundary Rules

`lotus-core` owns:

1. reconciliation run and finding truth,
2. control status vocabulary,
3. data-quality coverage evidence for core-owned products,
4. publish/release blocking flags derived from source truth,
5. supportability metadata used by downstream consumers.

`lotus-core` does not own:

1. performance attribution conclusions,
2. risk methodology decisions,
3. advisory suitability decisions,
4. report narrative interpretation,
5. UI-specific presentation of breaks.

## Gaps To Close Later

| Gap | Owner slice |
| --- | --- |
| Operator command for terminal finding resolution evidence | Future governed command slice |
| Product-specific freshness SLO calibration | Production closure |
| Product-level freshness SLOs | Slice 9 or production closure |
| Cross-consumer validation in `lotus-performance`, `lotus-risk`, and `lotus-gateway` | Slice 6 onward |

## Validation

Slice 5 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_reconciliation_quality.py -q`,
2. `python -m ruff check src/libs/portfolio-common/portfolio_common/reconciliation_quality.py tests/unit/libs/portfolio-common/test_reconciliation_quality.py --ignore E501,I001`,
3. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/reconciliation_quality.py tests/unit/libs/portfolio-common/test_reconciliation_quality.py`,
4. `git diff --check`,
5. `make lint`.
